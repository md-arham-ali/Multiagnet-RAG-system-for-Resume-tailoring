"""
Verifier - Groq llama-3.3-70b-versatile.

Extracts every claim, checks each is grounded in the retrieved evidence (NLI /
LLM-as-judge), and enforces the do-not-claim list exactly (exact + fuzzy match
over the WHOLE list). Grounding check, not generation. Prompt:
prompts/verifier/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, VerifierReport, VerifyStatus, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO (real logic):
      - extract claims from state.document, label supported | unsupported | contradicted,
      - exact/fuzzy-match the full do-not-claim list (rapidfuzz),
      - fail on ANY unsupported claim or do-not-claim hit -> loop back to Document,
      - return {"verifier_report": ...}.
    """
    # Placeholder skeleton: PASS so the Supervisor does NOT loop back yet.
    report = VerifierReport(status=VerifyStatus.PASS)
    return {"verifier_report": report, "stage": Stage.EVALUATION}
