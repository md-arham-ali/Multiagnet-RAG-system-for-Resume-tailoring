#!/usr/bin/env python3
"""
Demonstrate the Retriever (keyword + hybrid), the layers you wrote by hand in
vectordb/retriever.py. Prints semantic, keyword, and hybrid results side by
side for the same queries so you can compare how each layer ranks things.

Usage:  python scripts/demo_retriever.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vectordb import VectorStore, build
from vectordb.retriever import Retriever

QUERIES = [
    "Normalized token amounts, reserve configurations, and interest-rate states through dedicated preprocessing and transformation stages."
]


def show(label: str, hits) -> None:
    print(f"  {label}:")
    for h in hits:
        print(f"    {h.score:.3f}  [{h.metadata.get('type', '?'):<16}] {h.document[:80]}")
    if not hits:
        print("    (no hits)")


def main() -> int:
    store = VectorStore()
    if store.count("profile") == 0:
        print("Index empty — building it first ...\n")
        build(store)

    retriever = Retriever(store=store)
    where = {"type": "project"}  # only project evidence, not skills/education/etc.

    for q in QUERIES:
        print(f"\nquery: {q!r}")
        show("semantic", retriever.semantic("profile", q, k=5, where=where))
        show("keyword ", retriever.keyword("profile", q, k=5, where=where))
        show("hybrid  ", retriever.hybrid("profile", q, k=5, where=where))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
