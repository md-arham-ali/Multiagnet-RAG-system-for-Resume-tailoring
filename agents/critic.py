"""
Critic Agent - Gemini in eval mode, Groq in dev mode.

Reviews the Document output against a rubric the Supervisor passes at call time.
Returns pass/revise. Prompt: prompts/critic/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, Critique, Verdict, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO: score the document against the rubric, return
    pass | revise with actionable items. Supervisor loops back on revise.
    """
    # Stub. PASS so the loop-back stays off. Flip to REVISE to test it.
    critique = Critique(verdict=Verdict.PASS)
    return {"critique": critique, "stage": Stage.VERIFIER}
