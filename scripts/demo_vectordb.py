#!/usr/bin/env python3
"""
Vector DB demo: embed a sentence, then semantic search over the KB, including a
metadata-filtered one and the documents/learning collections.
Builds the index first if it's empty.

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

    # 1. the embedding step, made visible
    vec = store.embedder.embed(["applying machine learning on blockchain data"])[0]
    print(f"embedding dim = {len(vec)}  first 5 = {[round(x, 3) for x in vec[:5]]}")

    # 2. semantic search over profile evidence
    show("detect fraud and risk in blockchain lending pool",
         store.query("profile", "etect fraud and risk in blockchain lending pool", k=5))
    show("forecasting token prices over time for lending pools",
         store.query("profile", "forecasting token prices over time for lending pools", k=5))

    # 3. same query, filtered to one record type by metadata
    show("LSTM with pytorch  [type=skill only]",
         store.query("profile", "dLSTM with pytorch ", k=6, where={"type": "skill"}))

    # 4. the other two collections
    show("resume for a growth data analyst",
         store.query("documents", "resume for a growth data analyst", k=4))
    show("how to write quantified resume bullets",
         store.query("learning", "how to write quantified resume bullets", k=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
