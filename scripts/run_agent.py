#!/usr/bin/env python3
"""
Run one agent node, or a chain of them, without the graph. Each node's output is
threaded into the state the next one sees.

Anything a node needs that no earlier node produced gets seeded from PREREQS, and
only when still missing - real upstream output always wins.

Usage:  python scripts/run_agent.py                      # the COMPLETED chain
        python scripts/run_agent.py profile              # one agent, seeded
        python scripts/run_agent.py jd_analysis profile  # an explicit chain
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importlib import import_module

from pydantic import BaseModel

from state.state import GraphState, Requirement, Requirements
from state.state_utils import update_state

SAMPLE_JD = "We need a Python data engineer with strong SQL and ETL experience."

# Real agents, pipeline order. No-args runs exactly this chain.
# Append as each one stops being a stub.
COMPLETED = ["jd_analysis", "profile"]

# Stand-in for what jd_analysis would have produced, so downstream nodes can run
# on their own.
SAMPLE_REQUIREMENTS = Requirements(
    role_title="Data Engineer",
    seniority="fresher",
    keywords=["Python", "SQL", "ETL", "data pipeline"],
    requirements=[
        Requirement(text="Strong Python for data processing", kind="must_have",
                    category="hard_skill"),
        Requirement(text="SQL and relational data modelling", kind="must_have",
                    category="hard_skill"),
        Requirement(text="Build and maintain ETL pipelines", kind="must_have",
                    category="responsibility"),
        Requirement(text="Machine learning exposure", kind="nice_to_have",
                    category="hard_skill"),
    ],
)

# agent -> the state fields its node expects to be filled already
PREREQS: dict[str, dict] = {
    "profile": {"requirements": SAMPLE_REQUIREMENTS},
    "matching": {"requirements": SAMPLE_REQUIREMENTS},
    "document": {"requirements": SAMPLE_REQUIREMENTS},
}


def render(value) -> str:
    """Pretty-print: models as indented JSON, lists element by element."""
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    if isinstance(value, list):
        return "[\n" + "\n".join(f"  - {render(v)}" for v in value) + "\n]" if value else "[]"
    return str(value)


def seed_missing(state: GraphState, agent: str) -> GraphState:
    """Fill only the prereq fields still empty.

    In a chain an upstream agent already produced them for real, leave those
    alone. Running a node by itself, nothing did, so the sample stands in.
    """
    missing = {
        field: value
        for field, value in PREREQS.get(agent, {}).items()
        if getattr(state, field, None) is None
    }
    return update_state(state, **missing) if missing else state


def main() -> int:
    agents = sys.argv[1:] or COMPLETED

    state = GraphState(job_description=SAMPLE_JD)

    for agent in agents:
        module = import_module(f"agents.{agent}")
        state = seed_missing(state, agent)

        print(f"\n=== Running agent: {agent} ===")
        output = module.node(state)

        for key, value in output.items():
            print(f"\n{key}:\n{render(value)}")

        # thread this output into what the next node sees
        state = update_state(state, **output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())