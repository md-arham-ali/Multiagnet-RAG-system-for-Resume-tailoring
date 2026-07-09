#!/usr/bin/env python3
"""
Demonstrate the vector DB: embed a sentence, then run semantic searches over the
knowledge base — including a metadata-filtered search and the documents/learning
collections. Builds the index first if it is empty.

Usage:  python scripts/demo_vectordb.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vectordb import VectorStore, build


def show(title: str, hits) -> None:
    print(f"\n  query: {title!r}")
    for h in hits:
        print(f"    {h.score:.3f}  [{h.metadata.get('type', '?'):<16}] {h.document[:88]}")


def main() -> int:
    store = VectorStore()  # persistent
    if store.count("profile") == 0:
        print("Index empty — building it first ...\n")
        build(store)

    # 1) The embedding step, made visible.
    vec = store.embedder.embed(["applying machine learning on blockchain data"])[0]
    print(f"embedding dim = {len(vec)}  first 5 = {[round(x, 3) for x in vec[:5]]}")

    # 2) Semantic search over the profile evidence.
    show("detect fraud and risk in blockchain lending pool",
         store.query("profile", "etect fraud and risk in blockchain lending pool", k=5))
    show("forecasting token prices over time for lending pools",
         store.query("profile", "forecasting token prices over time for lending pools", k=5))

    # 3) Same query, filtered to a single record type via metadata.
    show("LSTM with pytorch  [type=skill only]",
         store.query("profile", "dLSTM with pytorch ", k=6, where={"type": "skill"}))

    # 4) The other tw    o collections.
    show("resume for a growth data analyst",
         store.query("documents", "resume for a growth data analyst", k=4))
    show("how to write quantified resume bullets",
         store.query("learning", "how to write quantified resume bullets", k=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
