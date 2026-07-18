"""
Critic Agent - Gemini 2.5 Flash in eval mode, Groq in dev mode.

Reviews the Document Agent's output against a RUBRIC the Supervisor passes at call
time, returning a typed pass/revise `Critique`. Prompt: prompts/critic/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, Critique, Verdict, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO (real logic):
      - score state.document against the rubric (relevance, evidence, template, ATS, readability),
      - return a typed Critique with verdict = pass | revise and actionable items,
      - Supervisor loops back to Document on 'revise' (capped by max_revisions).
    """
    # Placeholder skeleton: PASS so the Supervisor does NOT loop back yet.
    # (Flip this to Verdict.REVISE later to test the loop-back.)
    critique = Critique(verdict=Verdict.PASS)
    return {"critique": critique, "stage": Stage.VERIFIER}
