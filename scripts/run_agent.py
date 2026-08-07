#!/usr/bin/env python3
"""
Run one agent node, or a SEQUENCE of them, without the graph — each node's
output is threaded into the state the next node receives. Useful for developing
and testing the agents you have actually finished, in order.

Offline-friendly: prefix with USE_FAKE_LLM=1 to use the fake LLM (no API keys).
Any upstream input a node needs but no earlier node produced is seeded from
PREREQS below (only when still missing — real upstream output always wins).

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

# The agents with real brains, in pipeline order. Running with no arguments runs
# exactly this chain — append to it as each agent stops being a stub.
COMPLETED = ["jd_analysis", "profile"]

# Agents downstream of jd_analysis need state that an upstream agent would have
# produced. Seed it here so each node can be run in isolation, offline.
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

# agent name -> extra GraphState fields its node expects to already be filled.
PREREQS: dict[str, dict] = {
    "profile": {"requirements": SAMPLE_REQUIREMENTS},
    "matching": {"requirements": SAMPLE_REQUIREMENTS},
    "document": {"requirements": SAMPLE_REQUIREMENTS},
}


def render(value) -> str:
    """Pretty-print a value: Pydantic models as indented JSON, lists element-wise."""
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    if isinstance(value, list):
        return "[\n" + "\n".join(f"  - {render(v)}" for v in value) + "\n]" if value else "[]"
    return str(value)


def seed_missing(state: GraphState, agent: str) -> GraphState:
    """Fill only the prerequisite fields this agent needs that are still empty.

    In a chain, an upstream agent has usually produced them for real — those are
    left untouched. Running a node alone, nothing produced them, so the sample
    stands in.
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

        # Thread this node's output into the state the next node will see.
        state = update_state(state, **output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())