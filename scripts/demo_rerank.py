#!/usr/bin/env python3
"""
Two-stage retrieval: vector search for recall, cross-encoder rerank for
precision. Prints both orders so the effect is visible.

First run downloads the reranker model (BAAI/bge-reranker-base).

Usage:  python scripts/demo_rerank.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vectordb import Reranker, VectorStore, build


def row(h, attr: str) -> str:
    return f"    {getattr(h, attr):.3f}  [{h.metadata.get('type', '?'):<14}] {h.document[:78]}"


def main() -> int:
    store = VectorStore()
    if store.count("profile") == 0:
        print("Index empty — building it first ...\n")
        build(store)

    print("Loading reranker (BAAI/bge-reranker-base) ...")
    reranker = Reranker()
    query = "find at-risk loan positions before liquidation"

    vector_hits = store.query("profile", query, k=8)              # stage 1: recall
    reranked = reranker.rerank(query, list(vector_hits), top_k=5)  # stage 2: precision

    print(f"\nquery: {query!r}\n")
    print("  stage 1 — vector search (top 8 by embedding similarity):")
    for h in vector_hits:
        print(row(h, "score"))
    print("\n  stage 2 — reranked (top 5 by cross-encoder):")
    for h in reranked:
        print(row(h, "rerank_score"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
