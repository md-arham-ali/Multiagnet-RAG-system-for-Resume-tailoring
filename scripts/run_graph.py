#!/usr/bin/env python3
"""
Run the agent graph end-to-end on a sample job description and print the result.
Offline-friendly: prefix with USE_FAKE_LLM=1 to use the fake LLM (no API keys).

Usage:  python scripts/run_graph.py
        USE_FAKE_LLM=1 python scripts/run_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.supervisor import build_graph
from state.state import GraphState

# SAMPLE_JD = "We need a JAVA data engineer with strong OOps experience."
SAMPLE_JD = " WE need a python data engineer with must have strong MLops experience"


def _line(label: str, value: object) -> None:
    """Print one short summary line, truncating long values."""
    text = "—" if value is None else str(value)
    if len(text) > 100:
        text = text[:100] + "…"
    print(f"  {label:<16}: {text}")


def main() -> int:
    app = build_graph()
    result = app.invoke(GraphState(job_description=SAMPLE_JD))

    print("\n=== Graph run complete ===")
    print("final stage:", result.get("stage"))

    # 1 · JD Analysis
    reqs = result.get("requirements")
    print("\n[jd_analysis] requirements")
    if reqs:
        _line("role_title", reqs.role_title)
        for r in reqs.requirements:
            _line(r.kind, r.text)

    # 2 · Profile
    evidence = result.get("evidence") or []
    print(f"\n[profile] evidence ({len(evidence)} block(s))")
    for block in evidence:
        _line(block.source_id, block.content)

    # 3 · Matching
    fit = result.get("fit_report")
    print("\n[matching] fit_report")
    if fit:
        _line("overall_fit", fit.overall_fit)
        _line("must_have_cov", fit.must_have_coverage)

    # 4 · Document
    doc = result.get("document")
    print("\n[document] draft")
    if doc:
        _line("kind", doc.kind)
        _line("content", doc.content)

    # 5 · Critic
    crit = result.get("critique")
    print("\n[critic] critique")
    if crit:
        _line("verdict", crit.verdict)

    # 6 · Verifier
    vr = result.get("verifier_report")
    print("\n[verifier] report")
    if vr:
        _line("status", vr.status)

    # 7 · Evaluation
    ev = result.get("eval_record")
    print("\n[evaluation] record")
    if ev:
        _line("ats_score", ev.ats_score)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())