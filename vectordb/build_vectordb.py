"""
Build the vector DB: knowledge_base/*.json fixtures -> Chroma.

First run downloads the embedding model (~440 MB), index persists to
config.VECTORDB_DIR. Re-running is idempotent, it upserts.

Library only, runs nothing on import. Entry point: build_index().
Runner:  python scripts/build_vectordb.py
"""

from __future__ import annotations

from pathlib import Path

from vectordb.ingest import COLLECTIONS, build
from vectordb.store import VectorStore


def build_index(store: VectorStore | None = None, kb_dir: Path | None = None,
                reset: bool = True) -> tuple[dict[str, int], dict[str, int]]:
    """Index the KB. store=None -> persistent store at config.VECTORDB_DIR.
    Returns ({record_type: n indexed}, {collection: n vectors})."""
    store = store or VectorStore()
    counts = build(store, kb_dir=kb_dir, reset=reset)
    return counts, {col: store.count(col) for col in COLLECTIONS}
