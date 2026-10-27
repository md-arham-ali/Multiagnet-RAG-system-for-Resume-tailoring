"""
Matching Agent - Groq llama-3.3-70b-versatile.

Scores retrieved evidence against the typed requirements, out comes a FitReport.
Prompt: prompts/matching/system.yaml.

Split of labour inside this node: the LLM grades (which blocks support which
requirement, how strongly, why), the code does the arithmetic (coverage, overall
fit, unmet must-haves, ranking). A model asked for a float returns a vibe; the
same numbers derived from its own per-requirement grades are reproducible and
traceable, which is what the prompt's "every score must be traceable to a source
id" actually asks for.
"""

from __future__ import annotations

import json
import re

from agents.base import structured_call
from utils.prompt_loader import all_prompt_versions
from utils.trace import log
from state.state import (
    FitReport,
    GraphState,
    MatchAssessment,
    MatchGrade,
    MatchResult,
    ProfileBlock,
    Requirement,
    Stage,
    Support,
)

MUST_HAVE = "must_have"

# What a support grade is worth when it is averaged into a score.
SUPPORT_SCORE = {
    Support.STRONG: 1.0,
    Support.PARTIAL: 0.5,
    Support.NONE: 0.0,
}

# overall_fit = must_have coverage * this + nice_to_have coverage * (1 - this).
# A JD with only one kind of requirement scores on that kind alone.
MUST_HAVE_WEIGHT = 0.7

# How many blocks reach the Document Agent - the prompt's "sensible size budget".
EVIDENCE_BUDGET = 12

# Offline mode grades are built per call by _fake_json(). Live mode ignores them.
# Dealt round-robin so every support level appears: a one-grade offline answer
# never exercises the multi-item path (bugs.md #14 hid behind exactly that).
_FAKE_CYCLE = (Support.STRONG, Support.PARTIAL, Support.NONE)


def _fake_json(requirements: list[Requirement], evidence: list[ProfileBlock]) -> str:
    """The offline grade set, built from THIS run's requirements and evidence.

    A fixture frozen at import names requirements and ids belonging to no
    particular run, so _reconcile drops every citation and downgrades every grade:
    offline runs reported 0% fit, every must-have unmet, and Document's planner
    always saw nothing to grade (bugs_audit_fixed.md #46). Echoing the
    requirements we actually asked about and citing blocks that actually came
    back makes an offline run arithmetically shaped like a live one.

    Built per call, not at import, for the reason audit #14 gave: an import-time
    value is baked in for the whole process.
    """
    grades = []
    for n, req in enumerate(requirements):
        # Nothing retrieved means nothing citable, and _reconcile downgrades a
        # supported grade with no id anyway - grade 'none' rather than stage that.
        support = _FAKE_CYCLE[n % len(_FAKE_CYCLE)] if evidence else Support.NONE
        cited = (
            [evidence[n % len(evidence)].source_id]
            if support is not Support.NONE
            else []
        )
        grades.append(
            {
                "requirement_id": _req_id(n),
                "requirement": req.text,
                "support": support.value,
                "evidence_ids": cited,
                "justification": (
                    f"Offline fixture: graded '{support.value}' by position, not by "
                    "reading the evidence."
                ),
            }
        )
    return json.dumps({"matches": grades})


_KIND_SUFFIX = re.compile(r"\s*\[(?:must_have|nice_to_have)\]\s*$", re.IGNORECASE)

# "R1", "r1.", "R12)" at the start of a string - the label the prompt gives each
# requirement. Matched leniently because it is the model copying a label back.
_REQ_LABEL = re.compile(r"^\s*(R\d+)\s*[.):\-]?\s*", re.IGNORECASE)


def _req_id(index: int) -> str:
    """The label a requirement carries in THIS call's prompt. R1, R2, ... 1-based.

    Per call, never stored: the id is a pairing handle for one prompt/answer pair, so
    it needs no state field, no reducer and no checkpoint migration. Position is stable
    within a run because jd_analysis.node sanitises the list once, on the way into state.
    """
    return f"R{index + 1}"


def _split_label(text: str) -> tuple[str, str]:
    """-> (label, the rest) for "R1. Python", or ("", text) when there is no label.

    A label is only read off a text field when the requirement's own words follow it.
    A `requirement` of exactly "R5" is a requirement CALLED R5, not the label R5 with
    an empty text - and requirements named that way are not hypothetical: the pinned
    size test grades a hundred of them. Without this, "R5" would pair with R5's
    neighbour and every grade in that test would land one requirement off.
    """
    raw = text or ""
    found = _REQ_LABEL.match(raw)
    if not found:
        return "", raw
    rest = raw[found.end():]
    return (found.group(1).upper(), rest) if rest.strip() else ("", raw)


def _label_of(grade: MatchGrade) -> str:
    """The requirement label a grade claims, normalised, or "" if it claims none.

    Its own field first. Then a label prefixed to the requirement text, because a model
    that echoes the prompt line writes "R1. Python [must_have]" into `requirement` and
    leaves `requirement_id` empty - echoing the line is exactly what broke the live run
    (bug#116), so it is read, not punished.
    """
    found = _REQ_LABEL.match(grade.requirement_id or "")
    if found:
        return found.group(1).upper()
    return _split_label(grade.requirement)[0]


def _key(text: str) -> str:
    """Normalise a requirement string so the model's echo matches ours.

    The prompt shows each requirement as "R1. text [kind]", and gpt-oss-120b echoes the
    whole line. Live 2026-10-24 that paired nothing: every grade was thrown away and every
    requirement reported "Not graded". Label and suffix are stripped on both sides, so this
    still works as the second pairing route when the label is missing or wrong.
    """
    stripped = _split_label(text)[1]
    return " ".join(_KIND_SUFFIX.sub("", stripped).split()).lower()


def _pair(
    requirements: list[Requirement], grades: list[MatchGrade]
) -> tuple[dict[int, MatchGrade], int, int]:
    """Requirement index -> its grade. Returns (pairs, paired by label, paired by text).

    Two routes, label first. Pairing on the echoed TEXT alone is what made bug#116 a
    silent total loss: gpt-oss-120b echoed "Strong Python for data processing [must_have]",
    nothing matched, every requirement was recorded "Not graded" and the run finished green
    at fit 0.0. A label survives rewording; the text route survives a dropped label. A model
    has to get both wrong before a grade is lost, and the loss is then logged.

    One grade pairs with at most one requirement, and a requirement already paired by label
    is never re-paired by text - otherwise one grade's citations could be counted twice.
    """
    by_label = {_req_id(n): n for n in range(len(requirements))}
    pairs: dict[int, MatchGrade] = {}
    unlabelled: list[MatchGrade] = []

    for grade in grades:
        index = by_label.get(_label_of(grade))
        if index is None or index in pairs:
            # No label, a label for a requirement that does not exist, or a second
            # grade for one already answered. The text route gets a look at it.
            unlabelled.append(grade)
        else:
            pairs[index] = grade

    by_text: dict[str, MatchGrade] = {}
    for grade in unlabelled:
        by_text.setdefault(_key(grade.requirement), grade)

    by_label_count = len(pairs)
    for index, req in enumerate(requirements):
        if index not in pairs:
            found = by_text.pop(_key(req.text), None)
            if found is not None:
                pairs[index] = found

    return pairs, by_label_count, len(pairs) - by_label_count


def _build_prompt(requirements: list[Requirement], evidence: list[ProfileBlock]) -> str:
    """Evidence once with its ids, requirements once with their kind.

    Profile retrieved per requirement but state.evidence is flat - the
    requirement -> block map was never persisted. Rather than re-retrieve (paying
    for the same work twice), hand the model the whole scoped set and let the
    assignment be part of the judgement we are asking it for.
    """
    blocks = "\n".join(
        f"[{b.source_id}] ({b.category or 'uncategorised'}) {b.content}" for b in evidence
    )
    reqs = "\n".join(
        f"{_req_id(n)}. {r.text} [{r.kind}]" for n, r in enumerate(requirements)
    )
    return (
        "CANDIDATE EVIDENCE (cite blocks by the id in square brackets):\n"
        f"{blocks or '(no evidence retrieved)'}\n\n"
        "REQUIREMENTS TO SCORE (each is labelled R1, R2, ...):\n"
        f"{reqs}\n\n"
        "Grade every requirement above, exactly once each. Put its label in "
        "requirement_id, copied exactly. Cite only ids from the evidence list. "
        "If nothing supports a requirement, grade it 'none' and "
        "leave evidence_ids empty - do not stretch a block to cover it."
    )


def _reconcile(req: Requirement, graded: MatchGrade | None, known_ids: set[str]) -> MatchResult:
    """One requirement -> one MatchResult, built from what we already know.

    The caller loops over state.requirements, not over the model's list, so a
    requirement the model skipped shows up as unsupported instead of vanishing,
    and a requirement the model invented never enters the report at all. Only the
    judgement is taken from the model (bugs.md #14's lesson, applied here rather
    than repeated).
    """
    if graded is None:
        return MatchResult(
            requirement=req.text,
            kind=req.kind,
            support=Support.NONE,
            justification="Not graded by the model - recorded as unsupported.",
        )

    # An invented id cannot be traced back to a block, and an untraceable score is
    # the one thing this prompt forbids. Drop it rather than let it rank evidence.
    # One block cited twice is one citation: kept twice it counts twice in
    # _rank_evidence's "cited by more requirements" tie-break (#74 item 2).
    seen: set[str] = set()
    evidence_ids: list[str] = []
    unknown = 0
    for eid in graded.evidence_ids:
        if eid not in known_ids:
            unknown += 1
        elif eid not in seen:
            seen.add(eid)
            evidence_ids.append(eid)

    justification = graded.justification
    support = graded.support

    if support is not Support.NONE and not evidence_ids:
        # Graded as supported with nothing real to point at. Downgrade rather than
        # let an ungrounded grade reach Document as a claimable requirement.
        support = Support.NONE
        justification = (
            f"Downgraded to none: graded '{graded.support.value}' but no cited "
            f"evidence id exists in this run. {justification}"
        ).strip()
    elif unknown:
        justification = f"{justification} ({unknown} unknown evidence id(s) dropped.)".strip()

    if support is Support.NONE and evidence_ids:
        # "No support" and a list of supporting blocks cannot both be true, and the
        # list is what gate 3, the Critic and the Verifier read (#74 item 1).
        justification = (
            f"{justification} ({len(evidence_ids)} citation(s) dropped: a 'none' "
            "grade carries no support.)"
        ).strip()
        evidence_ids = []

    return MatchResult(
        requirement=req.text,
        kind=req.kind,
        support=support,
        evidence_ids=evidence_ids,
        justification=justification,
    )


def _mean_support(matches: list[MatchResult]) -> float:
    if not matches:
        return 0.0
    return sum(SUPPORT_SCORE[m.support] for m in matches) / len(matches)


def _overall_fit(matches: list[MatchResult]) -> float:
    """Must-haves and nice-to-haves averaged separately, then weighted together."""
    must = [m for m in matches if m.kind == MUST_HAVE]
    nice = [m for m in matches if m.kind != MUST_HAVE]
    if must and nice:
        score = (
            _mean_support(must) * MUST_HAVE_WEIGHT
            + _mean_support(nice) * (1 - MUST_HAVE_WEIGHT)
        )
    else:
        score = _mean_support(must or nice)
    return round(score, 3)


def _rank_evidence(matches: list[MatchResult], evidence: list[ProfileBlock]) -> list[str]:
    """Highest-signal blocks first, capped at EVIDENCE_BUDGET.

    Ranked from the grades, not by re-running the cross-encoder: the reranker
    scores relevance-to-query, not strength-as-CV-evidence (the distinction
    profile.node()'s design note draws), and Profile already reranked this set on
    the way in. What Document needs is which blocks the strongest requirements
    actually rest on.
    """
    best: dict[str, float] = {}
    cited: dict[str, int] = {}
    for m in matches:
        kind_weight = MUST_HAVE_WEIGHT if m.kind == MUST_HAVE else 1 - MUST_HAVE_WEIGHT
        weight = SUPPORT_SCORE[m.support] * kind_weight
        for eid in m.evidence_ids:
            best[eid] = max(best.get(eid, 0.0), weight)
            cited[eid] = cited.get(eid, 0) + 1

    # Retrieval order breaks ties, so the same grades always rank the same way.
    order = {b.source_id: i for i, b in enumerate(evidence)}
    ranked = sorted(
        (eid for eid, w in best.items() if w > 0),
        key=lambda eid: (-best[eid], -cited[eid], order.get(eid, len(order))),
    )
    return ranked[:EVIDENCE_BUDGET]


def node(state: GraphState) -> dict:
    """
    LangGraph node. One LLM pass grading every requirement against the retrieved
    evidence, then the fit arithmetic on top of those grades.
    """
    requirements = state.requirements.requirements if state.requirements else []
    evidence = state.evidence

    if not requirements:
        # Nothing to score. An empty report says so out loud (overall_fit 0.0)
        # rather than spending a call to have a model agree there is nothing here.
        return {"fit_report": FitReport(), "stage": Stage.CV_LINK}

    graded = structured_call(
        "matching",
        _build_prompt(requirements, evidence),
        MatchAssessment,
        fake_json=_fake_json(requirements, evidence),
    )

    known_ids = {b.source_id for b in evidence}
    pairs, by_label, by_text = _pair(requirements, graded.matches)
    # The model answered but not one grade paired with a requirement: every requirement would be recorded as
    # "Not graded", the fit report would read 0.0, and the run would carry on to the Critic as if that were a
    # result. That is exactly how the live run of 2026-10-23 completed with an empty report (bugs #116).
    if graded.matches and not pairs:
        raise ValueError(
            f"matching: the model returned {len(graded.matches)} grade(s) but none matched a requirement "
            f"by label or by text (it answered for "
            f"{[(g.requirement_id, g.requirement) for g in graded.matches][:3]}). Refusing to pass an "
            f"empty fit report downstream."
        )
    # A PARTIAL loss is the one bug#116 can still produce, and it is invisible in the report:
    # the lost requirements read "Not graded" -> unsupported -> unmet must-have, which then makes
    # Document's #59 guard refuse legitimate edits. Say so here, where the cause is still known.
    lost = len(requirements) - len(pairs)
    if lost or by_text:
        log(f"matching: {len(pairs)}/{len(requirements)} requirement(s) paired "
            f"({by_label} by label, {by_text} by text); {lost} not graded by the model")
    matches = [
        _reconcile(req, pairs.get(n), known_ids)
        for n, req in enumerate(requirements)
    ]

    report = FitReport(
        matches=matches,
        overall_fit=_overall_fit(matches),
        must_have_coverage=round(
            _mean_support([m for m in matches if m.kind == MUST_HAVE]), 3
        ),
        # "Unmet" means no evidence at all. A partial must-have is a weakness but
        # it is still claimable, and Document needs that distinction: an unmet
        # must-have is the one thing it must not write around.
        unmet_must_haves=[
            m.requirement
            for m in matches
            if m.kind == MUST_HAVE and m.support == Support.NONE
        ],
        ranked_evidence_ids=_rank_evidence(matches, evidence),
    )
    return {"fit_report": report, "prompt_versions": all_prompt_versions(["matching"]),
            "stage": Stage.CV_LINK}
