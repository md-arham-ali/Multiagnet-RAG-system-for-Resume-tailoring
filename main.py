"""
Entry point.

A preflight, not a runner: it validates configuration, prints the active model
assignment and proves every versioned prompt loads, all without a single API
call. Use it to find a bad .env before spending a run.

The pipeline itself is built elsewhere and has been since 07-05 — the supervisor
graph with its four human gates is `agents/supervisor.py:build_graph`, and the
gates are checkpointed to SQLite (`utils/checkpointer.py`, `config.CHECKPOINT_DB`;
the Postgres target in `config.DATABASE_URL` has no reader yet). To run it:

    python scripts/run_gated_graph.py     the whole pipeline, gates at the terminal
    python scripts/run_agent.py <agent>   one node, seeded, no graph
    python scripts/dev.py up              backend + frontend together

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
    print("Config OK. Run the pipeline with:  python scripts/run_gated_graph.py"
          "   (add USE_FAKE_LLM=1 to stay offline and free)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
