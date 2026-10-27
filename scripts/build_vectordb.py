#!/usr/bin/env python3
"""
Runner for vectordb/build_vectordb.py. Embeds knowledge_base/*.json into Chroma.
First run downloads the embedding model (~440 MB). Idempotent, it upserts.

Usage:  python scripts/build_vectordb.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from vectordb.build_vectordb import build_index  # noqa: E402


def main() -> int:
    print(f"Loading embedder: {config.EMBEDDING_MODEL}")
    print("Embedding + indexing the knowledge base ...")
    counts, collections = build_index()

    print("-" * 48)
    for rtype, n in counts.items():
        print(f"  {rtype:<18} {n:>4}")
    print("-" * 48)
    for col, n in collections.items():
        print(f"  collection '{col}': {n} vectors")
    print(f"\nPersisted to {config.VECTORDB_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
