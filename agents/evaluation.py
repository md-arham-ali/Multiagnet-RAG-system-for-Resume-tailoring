"""
Evaluation Agent - Groq llama-3.3-70b-versatile.

Runs AFTER final human approval. Scores the run (retrieval precision, ATS, fit,
generation quality) and writes an exemplar/score record to the Learning Store with
the prompt versions + learning slice used. Prompt: prompts/evaluation/system.yaml.

ATS part not yet impemented. TODO
"""

from __future__ import annotations

from state.state import GraphState, EvalRecord, Stage


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO (real logic):
      - compute ATS (evaluation.ats.keyword_coverage), retrieval precision (deepeval),
        fit, and LLM-as-judge generation scores,
      - attach prompt versions (utils.all_prompt_versions) + learning slice,
      - write to the Learning Store, return {"eval_record": ..., "stage": Stage.DONE}.
    """
    # Placeholder skeleton: return an empty EvalRecord and mark the run DONE.
    record = EvalRecord()
    return {"eval_record": record, "stage": Stage.DONE}
