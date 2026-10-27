#!/usr/bin/env python3
"""
THIS IS ON A TEST BASIS

CLI for the sandbox CV ingest. The logic lives in vectordb/cv_ingest.py.
Reads CV PDFs from knowledge_base/profile/input/ and embeds their chunks into the
SEPARATE sandbox index test_work/test_vb/. Nothing here touches knowledge_base/chroma/.

Usage:  python scripts/ingest_pdfs_test.py [--input DIR] [--index DIR]
Then:   python scripts/match_cv_test.py   (or scripts/rank_companies_test.py)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.cv_handling.cv_ingest import PDF_COLLECTION, indexed_chunks, ingest_cvs  # noqa: E402


def main() -> int:
    # Reads the command line, ingests every CV PDF in the input folder, prints the chunk counts.
    # out: exit code (0 ok, 1 no PDFs found)
    ap = argparse.ArgumentParser(description="Embed CV PDFs into the sandbox index.")
    ap.add_argument("--input", type=Path, default=config.CV_INPUT_DIR, help="folder of CV PDFs")
    ap.add_argument("--index", type=Path, default=config.CV_SANDBOX_DIR, help="sandbox Chroma folder")
    args = ap.parse_args()

    print(f"reading PDFs from : {args.input}")
    print(f"writing index to  : {args.index}\n")
    counts = ingest_cvs(args.input, args.index)
    if not counts:
        print(f"No *.pdf files found in {args.input}. Put the CVs there and re-run "
              f"(the sandbox index was left as it was).")
        return 1
    for name, n in counts.items():
        print(f"  {n:>4} chunks  <-  {name}")
    print(f"\n  total chunks indexed: {sum(counts.values())}")
    print(f"  chunks in '{PDF_COLLECTION}': {indexed_chunks(args.index)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
