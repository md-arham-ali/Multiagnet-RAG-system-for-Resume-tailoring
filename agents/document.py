"""
Document Agent - Gemini in eval mode, Groq in dev mode.

Writes the CV / cover letter from a template + matched evidence + the full
do-not-claim list. Output quality is the product. Prompt: prompts/document/system.yaml.
"""

from __future__ import annotations

from state.state import GraphState, Document, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO: pull a template, generate from ranked evidence only,
    inject the whole do-not-claim list, apply state.critique on a revision pass.
    """
    # Stub. Dummy draft, straight on to the Critic.
    draft = Document(kind="cv", content="(placeholder draft — real generation later)")
    return {"document": draft, "stage": Stage.CRITIC}
