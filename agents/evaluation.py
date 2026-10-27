"""
Evaluation Agent - Groq llama-3.3-70b-versatile.

Runs AFTER final approval. Scores the run and writes a record to the Learning
Store, tagged with the prompt versions + learning slice that produced it.
Prompt: prompts/evaluation/system.yaml.

ATS is NOT computed here. The checking module (evaluation/checks.py) computes it
and this node only reports it, as the prompt says ("computed deterministically
upstream - consume and report it"). Q7, bug #17.

Still mostly a stub: listed in backend/runs/worker.py STUB_NODES, so the UI labels
its output as placeholder. Real so far: ats_score (keyword check only) and
prompt_versions. Remove it from STUB_NODES in the same change that makes the rest real.
"""

from __future__ import annotations

from evaluation.checks import run_checks
from state.state import GraphState, EvalRecord, Stage
from utils.prompt_loader import all_prompt_versions


def node(state: GraphState) -> dict:
    """
    LangGraph node. TODO (stage H): retrieval precision, fit, an LLM-as-judge
    score, the learning slice, and the save to the Learning Store.
    """
    record = EvalRecord(
        ats_score=run_checks(state.requirements, state.document).ats_score,
        # It was computed by Matching and has been sitting in state the whole run;
        # leaving it None lost the number permanently, record by record (#77 item 2).
        fit_score=state.fit_report.overall_fit if state.fit_report else None,
        # Logged with every score, so a score that moves can be traced to the prompt.
        # Captured by jd_analysis when the run STARTED, not read off disk now: a
        # run can sit at gate 4 for days, across a restart and a prompt edit, and
        # the record has to name the version that actually produced the output
        # (#77 item 3). The fallback covers a state checkpointed before this field
        # existed, and chains that enter the graph past jd_analysis.
        prompt_versions=state.prompt_versions or all_prompt_versions(),
    )
    return {"eval_record": record, "stage": Stage.DONE}
