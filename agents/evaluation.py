"""
Evaluation Agent - Groq llama-3.3-70b-versatile.

Runs AFTER final approval. Scores the run and writes a record to the Learning
Store, tagged with the prompt versions + learning slice that produced it.
Prompt: prompts/evaluation/system.yaml.

ATS part not yet impemented. TODO
"""

from __future__ import annotations

from state.state import GraphState, EvalRecord, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO: ATS coverage, retrieval precision, fit, and an
    LLM-as-judge score. Attach prompt versions + learning slice, then save.
    """
    # Stub. Empty record, mark the run DONE.
    record = EvalRecord()
    return {"eval_record": record, "stage": Stage.DONE}
