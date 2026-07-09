#!/usr/bin/env python3
"""
Build the vector DB: embed the knowledge_base/*.json fixtures into Chroma.

First run downloads the embedding model (~440 MB) and persists the index to
config.VECTORDB_DIR. Re-running is idempotent (upsert).

Usage:  python scripts/build_vectordb.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from vectordb import VectorStore, build


def main() -> int:
    print(f"Loading embedder: {config.EMBEDDING_MODEL}")
    store = VectorStore()  # persistent
    print("Embedding + indexing the knowledge base ...")
    counts = build(store)

    print("-" * 48)
    for rtype, n in counts.items():
        print(f"  {rtype:<18} {n:>4}")
    print("-" * 48)
    for col in ("profile", "documents", "learning"):
        print(f"  collection '{col}': {store.count(col)} vectors")
    print(f"\nPersisted to {config.VECTORDB_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
