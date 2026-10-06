"""
Critic Agent - Gemini in eval mode, Groq in dev mode.

Reviews the Document output against a rubric the Supervisor passes at call time.
Returns pass/revise. Prompt: prompts/critic/system.yaml.
"""

from __future__ import annotations

import os

from agents.base import structured_call
from state.state import GraphState, Critique, Verdict, Stage


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

    requirements_text = "\n".join(
        f"- {r.text}" for r in state.requirements.requirements
    )

    user_input = (
        f"RUBRIC:\n{state.active_rubric}\n\n"
        f"REQUIREMENTS:\n{requirements_text}\n\n"
        f"FIT REPORT:\n{state.fit_report}\n\n"
        f"DOCUMENT:\n{state.document.content}"
    )

    result = structured_call(
        "critic",
        user_input,
        Critique,
        fake_json=_fake_json(),
    )

    
    return {"critique": result, "stage": Stage.VERIFIER}
