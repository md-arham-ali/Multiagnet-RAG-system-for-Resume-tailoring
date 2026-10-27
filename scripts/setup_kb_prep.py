#!/usr/bin/env python3
"""
Runner for utils/setup_kb_prep.py. Instructions.md steps 6 and 7.
Run after generate_kb_data.py, before build_vectordb.py. Idempotent.

Usage:  python scripts/setup_kb_prep.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.setup_kb_prep import prep  # noqa: E402


def main() -> int:
    n, folders = prep()
    print(f"Step 6: do_not_claim.txt written — {n} items, one per line")
    print("Step 7: per-agent learning subfolders (exemplars / corrections / feedback.jsonl):")
    for folder, (ex, co) in folders.items():
        print(f"  learning/{folder:<12} exemplars={ex:<3} corrections={co}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
