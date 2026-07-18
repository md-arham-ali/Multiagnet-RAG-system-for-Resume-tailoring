"""
Profile Agent - Groq llama-3.3-70b-versatile.

Retrieves relevant profile blocks for the requirements and runs the interactive
gap-interview (a human gate via interrupt()) to enrich the profile store.
Prompt: prompts/profile/system.yaml.
"""

# could not be tested and fully compelted until the vector database is built and integerated with the profiel

from __future__ import annotations

from state.state import GraphState, ProfileBlock, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. 
      - retrieve profile blocks per requirement (vector store, category filter),
      - identify gaps -> emit gap_questions, interrupt() for human answers,
      - upsert answers to the profile store,
      - return {"evidence": ..., "gap_questions": ..., "stage": Stage.MATCHING}.
    """

    profile = ProfileBlock(
        source_id = "just a placeholder",
        content = " this is just a test, real thing comes later",
        # category = "test",
        skills = ["hello", "world", "test"]

    )

    return {
        "evidence": [profile],
        "stage": Stage.MATCHING,
                }
    # raise NotImplementedError("profile.node is a scaffold — graph wiring is TODO.")
