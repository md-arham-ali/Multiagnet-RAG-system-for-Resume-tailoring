"""
Document Agent — Gemini 2.5 Flash in eval mode, Groq in dev mode.

Generates the tailored CV / cover letter from a template + the matched evidence
and the FULL do-not-claim list. Generation quality is the product here.
Prompt: prompts/document/system.yaml.
"""

from __future__ import annotations

from agents.base import spec_for
from state.state import GraphState, Document, Stage

SPEC = spec_for("document")


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO (real logic):
      - retrieve a template from the document store,
      - generate using only ranked matched evidence; inject the full do-not-claim list,
      - on a revision pass, apply state.critique feedback,
      - return {"document": ..., "stage": Stage.CRITIC}.
    """
    # Placeholder skeleton: return a dummy draft and advance to the Critic.
    draft = Document(kind="cv", content="(placeholder draft — real generation later)")
    return {"document": draft, "stage": Stage.CRITIC}
