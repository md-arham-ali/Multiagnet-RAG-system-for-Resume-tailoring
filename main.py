"""
Entry point.

For now this validates configuration and reports system status without making any
API calls — a fast way to confirm the scaffold is wired correctly. The LangGraph
build/run (supervisor + four human gates + Postgres checkpointer) is assembled in
a later milestone; see README.md and agents/supervisor.py:build_graph.

Usage:
    python main.py
"""

from __future__ import annotations

import sys

import config


def main() -> int:
    bar = "=" * 72
    print(bar)
    print(" Multi-agent CV / Cover-Letter system")
    print(bar)
    print(config.summary())
    print("-" * 72)

    # 1) Configuration check (missing keys are warnings, not fatal — the user
    #    fills them in .env). TEST_MODE being invalid IS reported here too.
    problems = config.validate()
    if problems:
        print("Config check: ATTENTION")
        for p in problems:
            print(f"  - {p}")
        print("  -> set these in .env before running the graph.")
    else:
        print("Config check: OK")

    # 2) Prove every versioned prompt loads (no API calls).
    try:
        from utils.prompt_loader import all_prompt_versions

        print("-" * 72)
        print("Prompt versions:")
        for agent, version in all_prompt_versions().items():
            print(f"    {agent:<12}-> v{version}  ({config.model_for(agent)})")
    except Exception as exc:  # surfacing a broken prompt file early is the point
        print(f"Prompt load FAILED: {exc}")
        return 1

    print("-" * 72)
    print("Scaffold OK. Next: wire the LangGraph supervisor + gates "
          "(agents/supervisor.py:build_graph). See README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
