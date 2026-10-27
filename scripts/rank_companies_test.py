#!/usr/bin/env python3
"""
SANDBOX: rank companies by how well they fit the CV (Approach B).

Direction matters and is easy to get backwards:
  CORPUS  = the CV, chunked, indexed in test_work/test_vb/
  QUERIES = each company blurb (Focus + What they do) from Companies.md

Per company, retrieve the best CV chunks and collapse them into ONE score via
company_score. Higher = that company's work is better covered by the CV.
Runs semantic AND hybrid so the two rankings can be compared.

Usage:  python scripts/rank_companies_test.py
Sandbox only, never touches knowledge_base/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vectordb.retriever import Retriever
from vectordb.store import VectorStore

COMPANIES_FILE = ROOT / "test_work" / "Companies.md"
INDEX_DIR = ROOT / "test_work" / "test_vb"
COLLECTION = "pdf_documents"

# how many top CV chunks feed company_score. the one knob.
TOP_K = 10
# how many companies to print per method
SHOW = 20


# --- plumbing: markdown tables -> (name, query_text) -------------------------
def load_companies(path: Path) -> list[dict]:
    """Every table row across the 3 Findings tables -> {name, query}.

    query = Focus + What-they-do. Focus carries the keyword signal, What-they-do
    carries the meaning.
    """
    header_idx: dict[str, int] = {}
    companies: list[dict] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]  # drop outer empties

        # header row redefines which column is which. keying by name means a
        # reordered column doesn't break this.
        if cells and cells[0] == "#" and "Company" in cells:
            header_idx = {name: i for i, name in enumerate(cells)}
            continue
        # separator row |---|---| -> skip
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        # data rows start with a number in the '#' column
        if not header_idx or not cells or not cells[0].isdigit():
            continue

        def col(substr: str) -> str:
            for name, i in header_idx.items():
                if substr.lower() in name.lower() and i < len(cells):
                    return cells[i]
            return ""

        raw_name = col("Company")
        m = re.search(r"\[([^\]]+)\]", raw_name)     # **[Name](url)** -> Name
        name = m.group(1) if m else raw_name.strip("* ")

        focus = col("Focus")
        what = col("What they do")
        query = f"{focus}. {what}".strip(". ").strip()
        if name and query:
            companies.append({"name": name, "query": query})

    return companies


# --- MY TUNABLE BLOCK (brain): hits -> one company score ---------------------
def company_score(hits) -> float:
    """Collapse a company's top CV chunks into one fit score.

    Currently max. mean vs max is the real design lever here:
      mean -> the company needs several CV chunks to be relevant
      max  -> one strongly relevant chunk is enough to rank it high
    Swap the return line to switch, and the print label in main() with it.
    """
    top = hits[:TOP_K]
    if not top:
        return 0.0
    return max(h.score for h in top)


# --- plumbing: score + rank every company for one method ---------------------
def rank(retriever: Retriever, companies: list[dict], method: str) -> list[dict]:
    """'semantic' or 'hybrid'. Companies best-first, each tagged with its score
    and its single best chunk, so you can see why it matched."""
    search = getattr(retriever, method)
    ranked = []
    for c in companies:
        hits = search(COLLECTION, c["query"], k=TOP_K)
        best = hits[0] if hits else None
        ranked.append({
            "name": c["name"],
            "score": company_score(hits),
            "why": (best.document[:70].replace("\n", " ") if best else ""),
            "why_chunk": (best.metadata.get("chunk_index") if best else None),
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


def main() -> int:
    store = VectorStore(persist_dir=INDEX_DIR)
    if store.count(COLLECTION) == 0:
        print("CV index is empty — run scripts/ingest_pdfs_test.py first.")
        return 1

    companies = load_companies(COMPANIES_FILE)
    print(f"parsed {len(companies)} companies from {COMPANIES_FILE.name}")
    print(f"CV chunks in index: {store.count(COLLECTION)}\n")

    # no reranker, so hybrid just merges+sorts. note audit #4: on this path the
    # keyword scale dominates cosine, so "hybrid" leans keyword.
    retriever = Retriever(store=store)

    for method in ("semantic", "hybrid"):
        print(f"\n===== ranking by {method} (max of top-{TOP_K}) =====")
        ranked = rank(retriever, companies, method)
        for i, r in enumerate(ranked[:SHOW], 1):
            print(f"{i:>2}. {r['score']:.3f}  {r['name']:<22} "
                  f"← CV chunk #{r['why_chunk']}: {r['why']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
