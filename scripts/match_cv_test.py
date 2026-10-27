#!/usr/bin/env python3
"""
CLI for CV -> profile source-id matching. The logic lives in vectordb/cv_extract.py
(parse) and vectordb/cv_match.py (match); see context/code_explanations.md.

Run after scripts/ingest_pdfs_test.py:
    python scripts/match_cv_test.py [--pdf CV_test.pdf] [--k 5] [--rebuild-bullets]
                                    [--input DIR] [--index DIR] [--out DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from utils.cv_handling.cv_match import BULLET_COLLECTION, K_CANDIDATES, match_cvs, resolve_pdfs  # noqa: E402


def main() -> int:
    # Reads the command line, picks the CVs, and runs the matching pipeline on them.
    # out: exit code (0 ok, 1 nothing to match or the profile index is unusable)
    ap = argparse.ArgumentParser(description="Match every CV line to profile source ids.")
    ap.add_argument("--pdf", help="one PDF (name in the input folder, or a path); default: every ingested CV")
    ap.add_argument("--k", type=int, default=K_CANDIDATES, help="candidates reported per line")
    ap.add_argument("--rebuild-bullets", action="store_true",
                    help=f"re-embed the sandbox '{BULLET_COLLECTION}' collection from the fixtures")
    ap.add_argument("--input", type=Path, default=config.CV_INPUT_DIR, help="folder the CV PDFs live in")
    ap.add_argument("--index", type=Path, default=config.CV_SANDBOX_DIR, help="sandbox Chroma folder")
    ap.add_argument("--out", type=Path, default=config.CV_MATCH_DIR, help="folder for the JSON outputs")
    args = ap.parse_args()

    pdfs = resolve_pdfs(args.pdf, args.input, args.index)
    if not pdfs:
        return 1
    results = match_cvs(pdfs, k=args.k, rebuild_bullets=args.rebuild_bullets,
                        out_dir=args.out, index_dir=args.index)
    return 0 if results is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
