"""
Matching Agent — Groq llama-3.3-70b-versatile.

Scores the retrieved profile evidence (sharpened by the bge reranker) against the
typed requirements and produces a `FitReport`. Prompt: prompts/matching/system.yaml.
"""

from __future__ import annotations

from agents.base import spec_for
from state.state import GraphState, FitReport, Stage

SPEC = spec_for("matching")


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO:
      - rerank evidence, score each requirement (strong | partial | none),
      - compute overall fit + must_have coverage, list unmet must-haves,
      - return {"fit_report": ..., "stage": Stage.DOCUMENT}.
    """

    report = FitReport(
        # matches = list[MatchResult] = Field(default_factory=list)
        overall_fit = 0.45,
        must_have_coverage = 0.5,
        unmet_must_haves = ["this is an emplty field"],
        # ranked_evidence_ids: list[str] = Field(default_factory=list)
    )

    return {"fit_report": report, "stage": Stage.DOCUMENT}
    # raise NotImplementedError("matching.node is a scaffold — graph wiring is TODO.")
