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

from agents.base import structured_call
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

# Offline mode returns this canned JSON. Live mode ignores it.
# Three requirements, one per support level, because a single-item fixture means
# the multi-item path never runs (bugs.md #14 hid behind exactly that).
_FAKE_JSON = (
    '{"matches": ['
    ' {"requirement": "Python", "support": "strong",'
    '  "evidence_ids": ["skill_000"],'
    '  "justification": "Skill block lists Python at advanced proficiency."},'
    ' {"requirement": "SQL", "support": "partial",'
    '  "evidence_ids": ["skill_001"],'
    '  "justification": "Reporting queries only, nothing production-scale."},'
    ' {"requirement": "ETL pipelines", "support": "none",'
    '  "evidence_ids": [],'
    '  "justification": "No block describes building or owning an ETL pipeline."}'
    ']}'
)


def _key(text: str) -> str:
    """Normalise a requirement string so the model's echo matches ours."""
    return " ".join((text or "").split()).lower()


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
    reqs = "\n".join(f"- {r.text} [{r.kind}]" for r in requirements)
    return (
        "CANDIDATE EVIDENCE (cite blocks by the id in square brackets):\n"
        f"{blocks or '(no evidence retrieved)'}\n\n"
        "REQUIREMENTS TO SCORE:\n"
        f"{reqs}\n\n"
        "Grade every requirement above, exactly once each. Cite only ids from the "
        "evidence list. If nothing supports a requirement, grade it 'none' and "
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
    evidence_ids = [eid for eid in graded.evidence_ids if eid in known_ids]
    dropped = len(graded.evidence_ids) - len(evidence_ids)
    justification = graded.justification
    support = graded.support

    if support != Support.NONE and not evidence_ids:
        # Graded as supported with nothing real to point at. Downgrade rather than
        # let an ungrounded grade reach Document as a claimable requirement.
        support = Support.NONE
        justification = (
            f"Downgraded to none: graded '{graded.support.value}' but no cited "
            f"evidence id exists in this run. {justification}"
        ).strip()
    elif dropped:
        justification = f"{justification} ({dropped} unknown evidence id(s) dropped.)".strip()

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
        fake_json=_FAKE_JSON,
    )

    known_ids = {b.source_id for b in evidence}
    by_requirement = {_key(g.requirement): g for g in graded.matches}
    matches = [
        _reconcile(req, by_requirement.get(_key(req.text)), known_ids)
        for req in requirements
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
    return {"fit_report": report, "stage": Stage.CV_LINK}
