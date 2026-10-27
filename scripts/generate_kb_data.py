#!/usr/bin/env python3
"""
Runner for utils/generate_kb_data.py. Writes the synthetic KB fixtures.
Overwrites the files under knowledge_base/, same seed = same data.

Usage:  python scripts/generate_kb_data.py [--n 50] [--small 10] [--agent-n 50] [--seed 42]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.generate_kb_data import generate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="samples for the standard schemas")
    ap.add_argument("--small", type=int, default=10,
                    help="samples for education / coursework / extracurriculars")
    ap.add_argument("--agent-n", type=int, default=50, help="prompt examples per agent")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"Generating KB test data (n={args.n}, small={args.small}, "
          f"agent_n={args.agent_n}, seed={args.seed})")
    print("-" * 66)
    written = generate(n=args.n, small=args.small, agent_n=args.agent_n, seed=args.seed)
    for path, count in written.items():
        label = "1 file (curated)" if path.parent.name == "do_not_claim" else f"{count} records"
        print(f"  {str(path.relative_to(ROOT)):<52} {label}")
    print("-" * 66)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
