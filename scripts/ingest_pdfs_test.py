#!/usr/bin/env python3
"""
THIS IS ON A TEST BASIS

Sandbox PDF ingest. Reads PDFs from test_work/, embeds chunks into a SEPARATE
index at test_work/test_vb/. Nothing here touches knowledge_base/chroma/.

Usage:  python scripts/ingest_pdfs_test.py
Query it with scripts/rank_companies_test.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vectordb.pdf_ingest import build_from_folder
from vectordb.store import VectorStore

PDF_DIR = ROOT / "test_work"
INDEX_DIR = ROOT / "test_work" / "test_vb"   # nested sandbox index


def main() -> int:
    # persist_dir is the SANDBOX dir, isolated from config.VECTORDB_DIR
    store = VectorStore(persist_dir=INDEX_DIR)

    print(f"reading PDFs from : {PDF_DIR}")
    print(f"writing index to  : {INDEX_DIR}\n")

    counts = build_from_folder(store, PDF_DIR)

    if not counts:
        print("No *.pdf files found in test_work/ — drop some in and re-run.")
        return 1

    total = 0
    for name, n in counts.items():
        print(f"  {n:>4} chunks  <-  {name}")
        total += n
    print(f"\n  total chunks indexed: {total}")
    print(f"  store.count('pdf_documents') = {store.count('pdf_documents')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
