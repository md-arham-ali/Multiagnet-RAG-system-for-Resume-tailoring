"""
Critic Agent - Gemini in eval mode, Groq in dev mode.

Reviews the Document output against a rubric the Supervisor passes at call time.
Returns pass/revise. Prompt: prompts/critic/system.yaml.
"""

from __future__ import annotations

import os
import re

from agents.base import structured_call
from utils.prompt_loader import all_prompt_versions
from utils.trace import log
from state.state import GraphState, Critique, CritiqueItem, Verdict, Stage


# Offline fixtures. TWO of them, because a single fixture never exercises the
# branch it does not take (Build.md addendum, bugs.md #14): the PASS path is what
# a normal offline run needs, and the REVISE path is the only way to reach the
# loop-back and Critique.items without hand-forcing a verdict, which is what the
# stage-B verification had to do.
#
# "approve" is not a Verdict - that vocabulary belongs to the human gates
# (approve | edit | reject). The Critic's enum is pass | revise (bugs.md #26).
_FAKE_PASS = '{"verdict": "pass", "items": []}'

# Multi-item on purpose: one finding per rubric dimension, two severities, so the
# offline path produces CritiqueItems that a reader can actually be tested against.
_FAKE_REVISE = (
    '{"verdict": "revise", "items": ['
    ' {"rubric_item": "Relevance", "severity": "major",'
    '  "location": "Summary, paragraph 1",'
    '  "instruction": "Open with the ETL pipeline experience the JD leads on;'
    ' the current summary is generic and buries it below the fold."},'
    ' {"rubric_item": "Evidence traceability", "severity": "major",'
    '  "location": "Experience, bullet 3",'
    '  "instruction": "The claim about scaling to millions of users matches no'
    ' evidence block. Cut it, or replace it with the figure the block states."},'
    ' {"rubric_item": "Readability", "severity": "minor",'
    '  "location": "Skills section",'
    '  "instruction": "Twelve comma-separated skills read as a keyword dump.'
    ' Group them under two or three headings."}'
    ']}'
)


def _fake_json() -> str:
    """Which verdict offline mode fakes.

    Read per call, not at import: an import-time env read bakes the value in for
    the whole process, which is the trap audit #14 cleared out of these modules.
    """
    if os.getenv("FAKE_CRITIC_VERDICT", "").strip().lower() == "revise":
        return _FAKE_REVISE
    return _FAKE_PASS


# Caps on the CHANGED LINES block. The Critic needs enough of each cited record
# to judge whether the line overstates it, not the whole record: an 18-block
# evidence list pasted whole dilutes the prompt and is paid for every lap.
EVIDENCE_CHARS = 400
MAX_CHANGED_LINES = 25


def _fit_text(state: GraphState) -> str:
    """The fit report as prose, not as a Python repr.

    f"{state.fit_report}" sent Pydantic's repr - one unbroken line of
    model_construct noise that the model has to parse before it can use any of
    it (bugs_audit_fixed.md #76 item 2).
    """
    fit = state.fit_report
    if fit is None:
        return "(not computed)"
    lines = [
        f"overall fit: {fit.overall_fit:.2f}",
        f"must-have coverage: {fit.must_have_coverage:.2f}",
    ]
    if fit.unmet_must_haves:
        lines.append("UNMET must-haves (the document must not claim these): "
                     + ", ".join(fit.unmet_must_haves))
    for m in fit.matches:
        lines.append(f"- [{m.kind}] {m.requirement}: {m.support.value}"
                     + (f" — {m.justification}" if m.justification else ""))
    return "\n".join(lines)


def _changed_lines_text(state: GraphState) -> str:
    """Every line Document rewrote, with the evidence records it cited.

    The rubric's traceability dimension judges whether a claim rests on a real
    evidence block - and the Critic was never shown one (#77 item 1). It also
    never learned WHICH lines are the agent's work: since the 10-06 rebuild
    Document patches the candidate's own CV, so most of DOCUMENT was written by
    the candidate and is not the agent's claim to defend. Only these lines are.
    """
    patches = state.document_patches
    if patches is None or not patches.edits:
        return "(no lines were changed: Document judged the CV already fit)"

    by_id = {b.source_id: b for b in state.evidence}
    out = []
    for edit in patches.edits[:MAX_CHANGED_LINES]:
        out.append(f"- line {edit.target_id} ({edit.action.value}, {edit.purpose.value})")
        if edit.new_text:
            out.append(f"  now reads: {edit.new_text}")
        if edit.reason:
            out.append(f"  Document's reason: {edit.reason}")
        if not edit.evidence_ids:
            out.append("  cites: NOTHING — nothing in the profile backs this line")
            continue
        for eid in edit.evidence_ids:
            block = by_id.get(eid)
            if block is None:
                # Matching's guards drop invented ids before they get here, so
                # this means the block left state, not that the model made it up.
                out.append(f"  cites {eid}: (record not in this run's evidence)")
            else:
                text = " ".join(block.content.split())[:EVIDENCE_CHARS]
                out.append(f"  cites {eid}: {text}")
    if len(patches.edits) > MAX_CHANGED_LINES:
        out.append(f"(+{len(patches.edits) - MAX_CHANGED_LINES} more changed lines not shown)")
    return "\n".join(out)


MAX_EVIDENCE_BLOCKS = 20


def _evidence_text(state: GraphState) -> str:
    """The run's evidence records, id first, capped.

    The rubric's traceability dimension needs the records themselves, not only
    the ids an edit cited: a changed line resting on the WRONG record, or on
    nothing when a fitting record was available, is only visible if the Critic
    can see what was on offer (#77 item 1).
    """
    if not state.evidence:
        return "(no evidence retrieved for this run)"
    out = []
    for block in state.evidence[:MAX_EVIDENCE_BLOCKS]:
        text = " ".join(block.content.split())[:EVIDENCE_CHARS]
        out.append(f"- {block.source_id}: {text}")
    if len(state.evidence) > MAX_EVIDENCE_BLOCKS:
        out.append(f"(+{len(state.evidence) - MAX_EVIDENCE_BLOCKS} more records not shown)")
    return "\n".join(out)


# The severity vocabulary, and the only one. state/state.py keeps `severity` a
# free string with these three words in a comment, and a Literal there would be
# worse than this sift: a model answering "critical" would fail validation
# INSIDE the structured call, so the whole critique - instruction and all -
# would be retried and then lost, instead of being read here with its severity
# corrected. One name for the set, so the sift and the prompt cannot drift.
SEVERITIES = ("info", "minor", "major")
DEFAULT_SEVERITY = "info"

# "N. Name - what to judge", the shape agents/supervisor.py STAGE_RUBRIC writes.
# Anchored at the start of a line so a number inside a sentence is not a heading.
_DIMENSION = re.compile(r"^\s*\d+\.\s+(.+?)\s+\u2014", re.MULTILINE)


def _norm(text: str) -> str:
    """Compare rubric names the way the rest of the pipeline compares strings.

    Twin of the `_key` helpers in agents/matching.py and agents/profile.py: the
    model echoes a dimension name back, and "Evidence Traceability" is the same
    dimension as "evidence traceability".
    """
    return " ".join((text or "").split()).lower()


def _dimensions(rubric: str) -> list[str]:
    """The dimension names of the rubric the Supervisor injected for THIS call.

    Returns [] for a rubric not written as a numbered list. The caller must read
    that as "cannot tell", never as "no dimensions" - a guard that cannot read
    its own rubric must not delete every finding the Critic made.
    """
    return _DIMENSION.findall(rubric or "")


def _sift(critique: Critique, rubric: str) -> Critique:
    """The Critic's answer reduced to what this system can act on.

    Structured output guarantees the SHAPE of a critique, never that its
    findings are about the rubric it was given (#76 item 6 - the same lesson as
    #14 and #58). Four rules, each logged, because a quietly edited verdict is
    harder to debug than a bad one:

      - A finding on a dimension this rubric does not list is dropped. The
        prompt already says "do not invent your own criteria"; without this,
        "Tone" forces a full redo for a dimension nobody asked for.
      - A severity outside SEVERITIES is read as the lowest one rather than
        dropped. The instruction is still a real finding, and `info` is the
        schema's own default, so nothing is invented.
      - A `revise` left with nothing to fix becomes a `pass`. decide() sends
        every revise back to Document, which would rewrite from the same input
        with no stated reason - and, until Document reads the critique (#76
        item 1), from a byte-identical prompt.
      - A `pass` carrying a major finding becomes a `revise`. Nothing
        downstream reads Critique.items yet (#19), so a major finding under a
        pass is a finding that disappears - and the rubric's major findings are
        unbacked claims.

    The last two are reversible calls: the alternative is to raise and let the
    run fail loudly. Logged so a reader can see which one fired.
    """
    dims = {_norm(d) for d in _dimensions(rubric)}
    if dims:
        items: list[CritiqueItem] = []
        for item in critique.items:
            if _norm(item.rubric_item) in dims:
                items.append(item)
            else:
                log(f"critic: dropped finding on {item.rubric_item!r}, "
                    f"not a dimension of this call's rubric")
    else:
        items = list(critique.items)
        log("critic: this rubric has no numbered dimensions, so every finding is kept")

    for i, item in enumerate(items):
        if item.severity not in SEVERITIES:
            log(f"critic: severity {item.severity!r} on {item.rubric_item!r} is not one of "
                f"{list(SEVERITIES)}; read as {DEFAULT_SEVERITY!r}")
            items[i] = item.model_copy(update={"severity": DEFAULT_SEVERITY})

    verdict = critique.verdict
    if verdict is Verdict.REVISE and not items:
        verdict = Verdict.PASS
        log("critic: revise with no finding left to act on, recorded as pass")
    elif verdict is Verdict.PASS and any(i.severity == "major" for i in items):
        verdict = Verdict.REVISE
        log("critic: pass carrying a major finding, recorded as revise")

    if verdict is critique.verdict and items == list(critique.items):
        return critique                      # nothing to correct: hand it on as it came
    return critique.model_copy(update={"verdict": verdict, "items": items})


def node(state: GraphState) -> dict:
    """
    LangGraph node. Reviews state.document against state.active_rubric,
    using state.requirements and state.fit_report as grounding context,
    and returns a structured Critique verdict.
    """

    if state.active_rubric is None:
        raise ValueError(
            "critic.node() called without an active_rubric — "
            "supervisor_node() must set state.active_rubric before routing here."
        )
    # requirements and document were bare AttributeErrors on a direct
    # run_agent.py chain (#60 item 1). fit_report was worse: it is the only
    # input that says which must-haves are unmet, and missing it the prompt
    # read "FIT REPORT:\nNone" and the call was paid for anyway (#76 item 2).
    if state.requirements is None or state.document is None or state.fit_report is None:
        missing = [n for n, v in (("requirements", state.requirements),
                                  ("document", state.document),
                                  ("fit_report", state.fit_report)) if v is None]
        raise ValueError(
            f"critic.node() needs state.{' and state.'.join(missing)}; "
            f"jd_analysis, matching and document run before it."
        )
    # An empty draft is not a review, it is a paid call with nothing to judge
    # (#76 item 2). document.node renders the patched CV tree, so a blank one
    # means the tree was lost, not that the CV is short.
    if not (state.document.content or "").strip():
        raise ValueError(
            "critic.node() was given an empty document; there is nothing to review. "
            "document.node renders the CV tree, so an empty draft is a bug upstream."
        )

    requirements_text = "\n".join(
        f"- {r.text}" for r in state.requirements.requirements
    )

    user_input = (
        f"RUBRIC:\n{state.active_rubric}\n\n"
        f"REQUIREMENTS:\n{requirements_text}\n\n"
        f"FIT REPORT:\n{_fit_text(state)}\n\n"
        f"EVIDENCE (the records retrieved from the candidate's profile for this "
        f"run):\n{_evidence_text(state)}\n\n"
        f"CHANGED LINES (the only lines Document wrote; everything else in "
        f"DOCUMENT is the candidate's own CV):\n{_changed_lines_text(state)}\n\n"
        f"DOCUMENT:\n{state.document.content}"
    )

    result = structured_call(
        "critic",
        user_input,
        Critique,
        fake_json=_fake_json(),
    )

    return {"critique": _sift(result, state.active_rubric),
            "prompt_versions": all_prompt_versions(["critic"]),
            "stage": Stage.VERIFIER}
