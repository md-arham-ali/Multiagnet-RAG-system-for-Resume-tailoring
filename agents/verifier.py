"""
Verifier - Groq llama-3.3-70b-versatile.

Pulls every claim out of the draft and checks it is grounded in the evidence.
Do-not-claim is matched over the WHOLE list, never top-k. Grounding, not generation.
Prompt: prompts/verifier/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, VerifierReport, VerifyStatus, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO: label each claim supported | unsupported | contradicted,
    fuzzy-match the do-not-claim list, fail on ANY hit and loop back to Document.
    """
    # Stub. PASS so the loop-back stays off.
    report = VerifierReport(status=VerifyStatus.PASS)
    return {"verifier_report": report, "stage": Stage.EVALUATION}
