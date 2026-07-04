#!/usr/bin/env python3
"""
Run a SINGLE agent node in isolation (no graph) and print what it returns.
Useful for developing and testing one agent at a time.
Offline-friendly: prefix with USE_FAKE_LLM=1 to use the fake LLM (no API keys).

Usage:  python scripts/run_agent.py              # defaults to jd_analysis
        python scripts/run_agent.py jd_analysis
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

from pydantic import BaseModel

from state.state import GraphState

SAMPLE_JD = "We need a Python data engineer with strong SQL and ETL experience."


def render(value) -> str:
    """Pretty-print a value: Pydantic models as indented JSON, lists element-wise."""
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    if isinstance(value, list):
        return "[\n" + "\n".join(f"  - {render(v)}" for v in value) + "\n]" if value else "[]"
    return str(value)


def main() -> int:
    agent = sys.argv[1] if len(sys.argv) > 1 else "jd_analysis"

    module = import_module(f"agents.{agent}")
    state = GraphState(job_description=SAMPLE_JD)

    print(f"\n=== Running agent: {agent} ===")
    output = module.node(state)

    for key, value in output.items():
        print(f"\n{key}:\n{render(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())