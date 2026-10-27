#!/usr/bin/env python3
"""
SANDBOX: agentic refinement on top of the CV-vs-companies ranking.

Wraps the deterministic base ranking from rank_companies_test.py in a small
supervisor -> refine -> critic loop. Same shape as the real graph, three nodes:

    base ranking -> REFINE (reorder to honor CHECKS) -> CRITIC (pass, or fail
    + feedback and loop back) -> final ranking

Two design points worth remembering:
  - checks are SEMANTIC TEXT only, soft preferences from the blurbs. No hard
    column filters.
  - the supervisor is plain Python, not an LLM. Same as supervisor_node in the
    real graph: a no-op hub with a deterministic route().

Both LLM steps go through structured_call, so USE_FAKE_LLM=1 runs the whole loop
offline (fake refine = identity order, fake critic = pass first try).

Usage:
    USE_FAKE_LLM=1 python scripts/agentic_rank_test.py   # offline structure test
    python scripts/agentic_rank_test.py                  # real Groq run
Edit CHECKS below to steer the ranking.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
from pydantic import BaseModel, Field

from agents.base import structured_call
from vectordb.retriever import Retriever
from vectordb.store import VectorStore

# reuse the base ranking, don't duplicate it
from scripts.rank_companies_test import (
    COLLECTION,
    INDEX_DIR,
    load_companies,
    rank,
)

# --- the checks I feed in (edit me) ------------------------------------------
CHECKS = """
Prioritize companies in the following order:

1. Strong Seed startups with clear product-market fit 
2. Series AB startups (Highest Priority)
3.  company domain lies in relation to Agentic AI/ Generative AI/ agent orchestration framework / multi-agent

Deprioritize:
- Pre-seed or idea-stage startups
- Large enterprises and legacy corporations
"""

REFINE_POOL = 80     # how many base-ranked companies enter the loop
MAX_REVISIONS = 5    # critic-fail cap, same idea as supervisor max_revisions
SHOW = 40


# --- schemas: what each agent must return ------------------------------------
class RefinedRanking(BaseModel):
    ranking: list[str] = Field(default_factory=list)   # company names, best first


class Critique(BaseModel):
    verdict: str = "pass"          # "pass" | "fail"
    feedback: str = ""
    issues: list[str] = Field(default_factory=list)


# --- helpers: format for the LLM, reorder by returned names ------------------
def _format(cands: list[dict], limit: int | None = None) -> str:
    rows = cands[: limit or len(cands)]
    return "\n".join(
        f"{i}. {c['name']} — {c['blurb'][:160]} (CV match: {c['cv_match'][:60]})"
        for i, c in enumerate(rows, 1)
    )


def _reorder_by_names(cands: list[dict], names: list[str]) -> list[dict]:
    """Reorder to what the refiner returned. Anything the LLM dropped or renamed
    falls to the end in its original order, so no company is ever lost."""
    by_name = {c["name"]: c for c in cands}
    ordered = [by_name[n] for n in names if n in by_name]
    seen = {c["name"] for c in ordered}
    ordered.extend(c for c in cands if c["name"] not in seen)
    return ordered


# --- REFINE: reorder candidates to honor the checks --------------------------
def refine(checks: str, cands: list[dict], feedback: str = "") -> list[dict]:
    user_input = f"USER CHECKS:\n{checks}\n\n"
    if feedback:
        user_input += f"CRITIC FEEDBACK FROM LAST ATTEMPT:\n{feedback}\n\n"
    user_input += f"CANDIDATES (current order):\n{_format(cands)}\n"

    result = structured_call(
        "rank_refiner", user_input, RefinedRanking,
        fake_json='{"ranking": []}',      # offline: empty -> identity order
    )
    return _reorder_by_names(cands, result.ranking)


# --- CRITIC: did the ranking honor the checks? -------------------------------
def critic(checks: str, cands: list[dict]) -> Critique:
    user_input = (
        f"USER CHECKS:\n{checks}\n\n"
        f"PROPOSED RANKING (top {SHOW}):\n{_format(cands, SHOW)}\n"
    )
    return structured_call(
        "rank_verifier", user_input, Critique,
        fake_json='{"verdict": "pass", "feedback": "[fake] pass", "issues": []}',
    )


# --- SUPERVISOR: run refine -> critic, capped by MAX_REVISIONS ---------------
class Supervisor:
    def __init__(self, max_revisions: int = MAX_REVISIONS) -> None:
        self.max_revisions = max_revisions

    def run(self, checks: str, candidates: list[dict]) -> tuple[list[dict], str, int]:
        order, feedback = candidates, ""
        for rev in range(self.max_revisions + 1):
            order = refine(checks, order, feedback)
            verdict = critic(checks, order)
            print(f"  [supervisor] revision {rev}: critic → {verdict.verdict.upper()}"
                  + (f"  ({verdict.feedback[:80]})" if verdict.feedback else ""))
            if verdict.verdict.lower() == "pass":
                return order, "pass", rev
            feedback = verdict.feedback
        return order, "fail(revisions exhausted)", self.max_revisions


def main() -> int:
    store = VectorStore(persist_dir=INDEX_DIR)
    if store.count(COLLECTION) == 0:
        print("CV index empty — run scripts/ingest_pdfs_test.py first.")
        return 1

    companies = load_companies(ROOT / "test_work" / "Companies.md")
    blurb_of = {c["name"]: c["query"] for c in companies}

    retriever = Retriever(store=store)
    base = rank(retriever, companies, "semantic")

    # candidate pool the agents work on
    candidates = [
        {"name": r["name"], "blurb": blurb_of.get(r["name"], ""),
         "cv_match": r["why"], "score": r["score"]}
        for r in base[:REFINE_POOL]
    ]

    mode = "FAKE LLM (offline)" if config.USE_FAKE_LLM else "REAL Groq"
    print(f"mode: {mode} | checks: {CHECKS!r}\n")
    print("===== BASE ranking (semantic, before checks) =====")
    for i, c in enumerate(candidates[:SHOW], 1):
        print(f"{i:>2}. {c['score']:.3f}  {c['name']}")

    print("\n===== AGENTIC refinement =====")
    final, status, revs = Supervisor().run(CHECKS, candidates)

    print(f"\n===== FINAL ranking ({status}, {revs} revision(s)) =====")
    for i, c in enumerate(final[:SHOW], 1):
        print(f"{i:>2}. {c['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
