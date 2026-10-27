"""
Small, fast tests for the vector DB.

These use a FAKE embedder (deterministic bag-of-words hashing) so they need no
model download and run in milliseconds — they test the store/ingest *logic*, not
embedding quality. One opt-in test exercises the real bge-base model:

    RUN_REAL_EMBED=1 .venv/bin/python -m pytest tests/test_vectordb.py

The sections after the original tests cover the whole KB + semantic search +
RAG lane the same way (fake embedder, stub reranker, tmp_path): the store's
contract, the Retriever's channels, the /api/search and KB-browser routes,
lookup.profile_blocks, ingest + build_index, pdf_ingest and the CV sandbox, the
record types every writer and reader agree on, the real knowledge_base/
fixtures (read-only), the KB generator and prep, and the scripts/ runners.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import itertools
import json
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import config
from backend.routes import kb as kb_routes
from learning import profile_store
from learning import store as learning_store
from state.state import ProfileBlock, SectionType
from utils import generate_kb_data, setup_kb_prep
from utils.cv_handling.cv_ingest import SECTION_TO_KB_TYPE
from vectordb import ingest, lookup, pdf_ingest
from vectordb.build_vectordb import build_index
from vectordb.retriever import Retriever
from vectordb.store import CollectionNotFound, VectorStore

DIM = 128


def _tokens(text: str) -> list[str]:
    clean = "".join(c.lower() if c.isalnum() else " " for c in text)
    return clean.split()


class FakeEmbedder:
    """Deterministic, no-download embedder: hashes tokens into a normalized
    multi-hot vector, so texts that share words get similar vectors."""

    model_name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        hits = []
        for text in texts:
            v = [0.0] * DIM
            for tok in _tokens(text):
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM
                v[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            hits.append([x / norm for x in v])
        return hits


@pytest.fixture
def store():
    s = VectorStore(embedder=FakeEmbedder(), in_memory=True)
    # Guarantee isolation even if Chroma caches the in-memory client.
    for c in s.client.list_collections():
        s.client.delete_collection(c if isinstance(c, str) else c.name)
    return s


# --- embedder ----------------------------------------------------------------
def test_embedding_is_deterministic_and_normalized():
    e = FakeEmbedder()
    a = e.embed(["python sql data"])[0]
    b = e.embed(["python sql data"])[0]
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9


# --- store: add / count / query / filter / upsert ----------------------------
def test_add_and_count(store):
    store.add("items", ["1", "2"], ["python developer", "graphic designer"],
              [{"type": "skill"}, {"type": "skill"}])
    assert store.count("items") == 2


def test_query_ranks_by_similarity(store):
    store.add(
        "items",
        ["py", "art", "ml"],
        ["python sql data engineering", "graphic design photoshop art",
         "machine learning python models"],
        [{"type": "a"}, {"type": "a"}, {"type": "a"}],
    )
    hits = store.query("items", "python data science", k=3)
    assert hits[0].id == "py"                       # most shared words
    assert hits[0].score >= hits[-1].score          # sorted by similarity
    assert 0.0 <= hits[0].score <= 1.0
    assert hits[0].metadata["type"] == "a"


def test_metadata_filter(store):
    store.add("items", ["a", "b"], ["python", "python"],
              [{"type": "skill"}, {"type": "project"}])
    hits = store.query("items", "python", k=5, where={"type": "project"})
    assert [h.id for h in hits] == ["b"]


def test_upsert_is_idempotent(store):
    store.add("items", ["a"], ["python"], [{"type": "skill"}])
    store.add("items", ["a"], ["python and rust"], [{"type": "skill"}])
    assert store.count("items") == 1


def test_query_on_a_collection_nobody_built_raises_instead_of_returning_nothing(store):
    with pytest.raises(CollectionNotFound):
        store.query("nope", "anything", k=3)


# --- ingest: builds ids/text/metadata from the real fixtures (fake embedder) --
def test_ingest_builds_collections_from_kb(store):
    counts = ingest.build(store)
    assert counts.get("project", 0) >= 1
    # profile collection holds several record types
    assert store.count("profile") == sum(
        counts.get(t, 0) for t in
        ("project", "work_experience", "education", "skill",
         "coursework", "achievement", "extracurricular") + tuple(RUNTIME_TYPES)   # + user-written records, if any
    )
    hit = store.query("profile", "python machine learning project", k=1)[0]
    assert hit.id.startswith(hit.metadata["type"] + ":")
    assert "source_id" in hit.metadata


def test_ingest_text_builders_are_nonempty():
    sample = {
        "basic_info": {"title": "Aave Risk Monitor", "domain": ["DeFi"]},
        "problem": {"business_problem": "rank lending risk"},
        "skills_demonstrated": ["Python", "SQL"],
        "resume_material": {"one_line": "Built a DeFi risk monitor."},
    }
    text = ingest._project_text(sample)
    assert "Aave Risk Monitor" in text and "DeFi" in text and "Python" in text


# --- opt-in: real bge-base model (downloads ~440 MB on first run) -------------
@pytest.mark.skipif(os.getenv("RUN_REAL_EMBED") != "1",
                    reason="set RUN_REAL_EMBED=1 to run the real embedding model")
def test_real_embedder_semantic_search():
    from vectordb import Embedder

    s = VectorStore(embedder=Embedder(), in_memory=True)
    s.add("items", ["chain", "bread"],
          ["smart contract security audit on ethereum",
           "a recipe for baking sourdough bread"],
          [{"type": "a"}, {"type": "a"}])
    hits = s.query("items", "blockchain vulnerability analysis", k=2)
    assert hits[0].id == "chain"        # semantically closest, not word overlap
    assert hits[0].score > hits[1].score


# --- reranker ----------------------------------------------------------------
from vectordb.store import Hit
from vectordb.reranker import Reranker


class StubReranker(Reranker):
    """Exercises the REAL Reranker.rerank ordering logic without a model download:
    only score() is stubbed (token overlap between query and document)."""

    def __init__(self):
        pass  # skip the CrossEncoder model load

    def score(self, query, documents):
        q = set(_tokens(query))
        return [float(len(q & set(_tokens(d)))) for d in documents]


def _hit(id_, doc):
    return Hit(id=id_, document=doc, metadata={"type": "a"}, score=0.5, distance=0.5)


def test_reranker_reorders_and_sets_score():
    rr = StubReranker()
    hits = [_hit("1", "graphic design art"),
            _hit("2", "python sql data pipeline"),
            _hit("3", "python machine learning")]
    hits = rr.rerank("python data", hits)
    assert hits[0].id == "2"                          # 2 shared tokens (python, data)
    assert hits[0].rerank_score >= hits[-1].rerank_score
    assert all(h.rerank_score is not None for h in hits)


def test_reranker_respects_top_k():
    hits = [_hit(str(i), "python data") for i in range(5)]
    assert len(StubReranker().rerank("python", hits, top_k=2)) == 2


def test_reranker_handles_empty():
    assert StubReranker().rerank("q", []) == []


def test_search_with_reranker_fetches_then_cuts(store):
    store.add("items", ["a", "b", "c"],
              ["python sql data", "python machine learning models", "graphic design"],
              [{"type": "x"}, {"type": "x"}, {"type": "x"}])
    hits = store.search("items", "python data science", k=2, fetch=3, reranker=StubReranker())
    assert len(hits) == 2
    assert hits[0].id == "a"                          # most query-token overlap
    assert hits[0].rerank_score is not None


def test_search_without_reranker_is_plain_vector_query(store):
    store.add("items", ["a", "b"], ["python sql", "graphic art"],
              [{"type": "x"}, {"type": "x"}])
    hits = store.search("items", "python", k=1)
    assert len(hits) == 1 and hits[0].rerank_score is None


@pytest.mark.skipif(os.getenv("RUN_REAL_RERANK") != "1",
                    reason="set RUN_REAL_RERANK=1 to run the real bge-reranker model")
def test_real_reranker_improves_relevance():
    from vectordb import Embedder

    s = VectorStore(embedder=Embedder(), in_memory=True)
    s.add("items_real", ["risk", "bread", "wallet"],
          ["assess credit risk for DeFi lending positions",
           "a recipe for baking sourdough bread",
           "detect anomalous crypto wallet activity"],
          [{"type": "a"}, {"type": "a"}, {"type": "a"}])
    hits = s.search("items_real", "find risky loan positions in DeFi",
                   k=2, fetch=3, reranker=Reranker())
    assert hits[0].id == "risk"
    assert hits[0].rerank_score is not None

##retrieval------------------------------------------------------------------------------------------------------
def test_keyword_ranks_by_term_overlap(store):
    from vectordb.retriever import Retriever
    store.add("items", ["a", "b", "c"],
              [
            "python sql data pipeline",
            "graphic design photoshop",
            "python machine learning models"],
            [{"type": "x"}, {"type": "x"}, {"type": "x"}]
    )

    r = Retriever(store = store)
    hits = r.keyword("items", "python data", k= 2)

    assert hits[0].id == "a"
    assert len(hits) == 2

def test_hybrid_dedupes_and_ranks(store):
    from vectordb.retriever import Retriever
    store.add("items",
              ["a", "b", "c"],
              ["python sql data pipeline", "python machine learning", "graphic design"],
              [{"type": "x"}, {"type": "x"}, {"type": "x"}])

    r = Retriever(store=store)            
    hits = r.hybrid("items", "python data", k=2)

    ids = [h.id for h in hits]
    assert len(ids) == len(set(ids))    
    assert len(hits) == 2


def test_hybrid_uses_reranker_when_present(store):
    from vectordb.retriever import Retriever
    store.add("items", ["a", "b", "c"],
              [
            "python sql data pipeline",
            "graphic design photoshop",
            "python machine learning models"],
            [{"type": "x"}, {"type": "x"}, {"type": "x"}]
    )

    r = Retriever(store = store, reranker = StubReranker())

    hits = r.hybrid("items", "python data science", k = 2)

    assert hits[0].rerank_score is not None
    assert len(hits) == 2


# =============================================================================
# Shared helpers for the sections below
# =============================================================================
ROOT = Path(__file__).resolve().parent.parent
ADMIN = {"identifier": "admin", "role": "admin", "runs_remaining": None, "token_id": "__admin__"}

TYPE_COLLECTION = {rtype: col for _, _, rtype, col, _, _ in ingest.SOURCES}
ALL_TYPES = set(TYPE_COLLECTION)
# Written by users at run time (knowledge_base/profile/manual_entries.json: gap answers, Build Profile). Present on a
# dev machine, absent in a clean checkout (CI), so no test may depend on how many there are.
RUNTIME_TYPES = {"build_profile", "gap_answer"}
PROFILE_TYPES = {t for t, col in TYPE_COLLECTION.items() if col == "profile"}
SMALL_TYPES = {"education", "coursework", "extracurricular"}      # generate(small=...)


def _x(n: int) -> list[dict]:
    return [{"type": "x"} for _ in range(n)]


def _ids(store, collection: str) -> set[str]:
    return set(store._collection(collection).get()["ids"])


def _names(store) -> set[str]:
    return {c.name for c in store.client.list_collections()}


ROWS = [
    ("p1", "python sql data pipeline airflow", "project"),
    ("p2", "graphic design photoshop", "project"),
    ("s1", "python pandas numpy", "skill"),
    ("s2", "sql postgres", "skill"),
    ("e1", "msc data science python", "education"),
    ("g1", "queried large sql tables in python", "gap_answer"),
]


def _seed(store, rows=ROWS, collection: str = "kb_test") -> None:
    store.add(collection, [r[0] for r in rows], [r[1] for r in rows], [{"type": r[2]} for r in rows])


class SpyReranker(StubReranker):
    """The real rerank ordering (via StubReranker), plus a record of every call."""

    def __init__(self):
        self.calls = []

    def rerank(self, query, hits, top_k=None):
        self.calls.append((query, [h.id for h in hits], top_k))
        return super().rerank(query, hits, top_k=top_k)


class AxisEmbedder:
    """'up' and anything else map to opposite unit vectors: the one case where
    cosine distance reaches 2."""

    def embed(self, texts):
        return [[1.0, 0.0] if t == "up" else [-1.0, 0.0] for t in texts]


def _mini_kb(root: Path) -> Path:
    """A tiny KB tree in the real layout: two types share a raw id, one record
    has an empty metadata field, and do-not-claim sits beside the vector stores."""
    files = {
        "profile/projects.json": [
            {"project_id": "p1", "basic_info": {"title": "Aave Risk Monitor", "domain": ["DeFi"]},
             "skills_demonstrated": ["Python", "SQL"], "resume_material": {"one_line": "Built a DeFi risk monitor."}},
            {"project_id": "p2", "basic_info": {}},
        ],
        "profile/skills.json": [{"skill_id": "p1", "name": "Python", "category": "language"}],
        "profile/education.json": [{"education_id": "e1", "degree": "MSc", "major": "Data Science", "institution": "TU"}],
        "documents/cv_examples.json": [{"example_id": "cv1", "target_role": "Data Engineer", "industry": "Fintech"}],
        "learning/agent_learnings.json": [{"learning_id": "l1", "agent_name": "critic",
                                           "lesson": {"summary": "Quantify every bullet."}}],
        "do_not_claim/do_not_claim.json": {"forbidden_claims": [{"id": "dnc_000", "claim": "PhD in Computer Science"}]},
    }
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return root


# =============================================================================
# vectordb/store.py - the store's contract
# =============================================================================
def test_query_hits_carry_the_exact_record_and_a_consistent_score(store):
    store.add("items", ["a", "b"], ["python sql data", "graphic design"],
              [{"type": "skill", "n": 1}, {"type": "art", "flag": True}])
    hits = store.query("items", "python sql", k=2)
    by_id = {h.id: h for h in hits}
    assert (by_id["a"].document, by_id["a"].metadata) == ("python sql data", {"type": "skill", "n": 1})
    assert by_id["b"].metadata == {"type": "art", "flag": True}          # scalars keep their types
    for h in hits:
        assert abs(h.score + h.distance - 1.0) < 2e-4                     # score = 1 - distance, both rounded
        assert h.rerank_score is None
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_k_caps_the_hits_and_a_small_collection_returns_what_it_has(store):
    store.add("items", [str(i) for i in range(6)], [f"python item {i}" for i in range(6)], _x(6))
    assert len(store.query("items", "python", k=3)) == 3
    assert len(store.query("items", "python", k=50)) == 6


def test_a_filter_that_matches_nothing_returns_nothing(store):
    store.add("items", ["a"], ["python"], [{"type": "skill"}])
    assert store.query("items", "python", k=3, where={"type": "project"}) == []


def test_an_in_filter_returns_only_the_listed_types(store):
    # The exact filter shape agents/profile.py sends for every quota group.
    store.add("items", ["s", "p", "e", "g"], ["python"] * 4,
              [{"type": "skill"}, {"type": "project"}, {"type": "education"}, {"type": "gap_answer"}])
    hits = store.query("items", "python", k=10, where={"type": {"$in": ["skill", "gap_answer"]}})
    assert sorted(h.id for h in hits) == ["g", "s"]


def test_add_rejects_mismatched_lengths_and_writes_nothing(store):
    store.add("items", ["a"], ["python"], _x(1))
    with pytest.raises(Exception):
        store.add("items", ["b", "c"], ["only one text"], _x(1))
    assert store.count("items") == 1


def test_upsert_replaces_the_text_and_metadata_not_just_the_count(store):
    store.add("items", ["a"], ["python"], [{"type": "skill"}])
    store.add("items", ["a"], ["rust systems"], [{"type": "project"}])
    (hit,) = store.query("items", "rust", k=1)
    assert (hit.document, hit.metadata) == ("rust systems", {"type": "project"})
    assert store.query("items", "python", k=1, where={"type": "skill"}) == []     # the old version is gone


def test_reset_drops_only_its_collection_and_tolerates_a_missing_one(store):
    store.add("one", ["a"], ["python"], _x(1))
    store.add("two", ["b"], ["python"], _x(1))
    store.reset("one")
    store.reset("never-existed")                                          # a no-op, never an error
    assert "one" not in _names(store) and store.count("two") == 1


def test_a_second_store_on_the_same_folder_sees_the_vectors(tmp_path):
    first = VectorStore(embedder=FakeEmbedder(), persist_dir=tmp_path / "chroma")
    first.add("items", ["a"], ["python sql"], [{"type": "skill"}])
    second = VectorStore(embedder=FakeEmbedder(), persist_dir=tmp_path / "chroma")
    assert second.query("items", "python", k=1)[0].id == "a"
    assert (tmp_path / "chroma" / "chroma.sqlite3").is_file()


def test_the_in_memory_store_never_sees_a_persistent_one(store, tmp_path):
    disk = VectorStore(embedder=FakeEmbedder(), persist_dir=tmp_path / "chroma")
    disk.add("items", ["disk"], ["python"], _x(1))
    assert store.count("items") == 0


def test_rerank_keeps_input_order_on_ties():
    ranked = StubReranker().rerank("python", [_hit(str(i), "python data") for i in range(4)])
    assert [h.id for h in ranked] == ["0", "1", "2", "3"]                 # sorted() is stable


def test_hit_score_stays_in_its_documented_range():
    s = VectorStore(embedder=AxisEmbedder(), in_memory=True)
    s.reset("axis")
    s.add("axis", ["up"], ["up"], _x(1))
    (hit,) = s.query("axis", "down", k=1)
    assert 0.0 <= hit.score <= 1.0


@pytest.mark.parametrize("read", ["query", "search", "count", "semantic", "keyword", "hybrid", "api_search"])
def test_a_read_never_creates_a_collection(store, monkeypatch, read):
    monkeypatch.setattr(kb_routes, "get_vector_store", lambda: store)
    r = Retriever(store=store)
    call = {
        "query": lambda: store.query("never_built", "python", k=3),
        "search": lambda: store.search("never_built", "python", k=3),
        "count": lambda: store.count("never_built"),
        "semantic": lambda: r.semantic("never_built", "python"),
        "keyword": lambda: r.keyword("never_built", "python"),
        "hybrid": lambda: r.hybrid("never_built", "python"),
        "api_search": lambda: kb_routes.search(kb_routes.SearchRequest(query="python", collection="never_built"), ADMIN),
    }[read]
    try:
        call()
    except Exception:
        pass                                    # refusing loudly is a fine fix; creating it is not
    assert "never_built" not in _names(store)


# =============================================================================
# vectordb/retriever.py - the channels the agents call
# =============================================================================
def test_semantic_is_the_store_query(store):
    _seed(store)
    r = Retriever(store=store)
    where = {"type": {"$in": ["skill", "project"]}}
    assert r.semantic("kb_test", "python sql", k=3, where=where) == store.query("kb_test", "python sql", k=3, where=where)


def test_reranked_without_a_reranker_is_plain_top_k(store):
    _seed(store)
    assert Retriever(store=store).reranked("kb_test", "python sql", k=2, fetch=5) == store.query("kb_test", "python sql", k=2)


def test_reranked_fetches_wide_then_cuts_to_k(store):
    _seed(store)
    spy = SpyReranker()
    hits = Retriever(store=store, reranker=spy).reranked("kb_test", "python sql", k=2, fetch=5)
    ((query, seen, top_k),) = spy.calls
    assert (query, len(seen), top_k) == ("python sql", 5, 2)
    assert len(hits) == 2 and all(h.rerank_score is not None for h in hits)
    assert [h.rerank_score for h in hits] == sorted((h.rerank_score for h in hits), reverse=True)


def test_keyword_scores_in_range_respects_the_filter_and_k(store):
    _seed(store)
    r = Retriever(store=store)
    hits = r.keyword("kb_test", "python sql", k=10, where={"type": "skill"})
    assert sorted(h.id for h in hits) == ["s1", "s2"]
    assert all(0.0 <= h.score <= 1.0 for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert len(r.keyword("kb_test", "python sql", k=2)) == 2


def test_keyword_with_a_filter_that_matches_nothing_returns_nothing(store):
    _seed(store)
    assert Retriever(store=store).keyword("kb_test", "python", where={"type": "achievement"}) == []


def test_keyword_returns_fresh_hits_every_call(store):
    _seed(store)
    r = Retriever(store=store)
    r.keyword("kb_test", "python", k=3)[0].score = -5.0                          # a caller scribbles on a hit
    assert all(h.score >= 0 for h in r.keyword("kb_test", "python", k=3))


def test_keyword_matching_ignores_case(store):
    store.add("kb_test", ["exact", "near"], ["PYTHON SQL", "pythons sqlite"], _x(2))
    assert Retriever(store=store).keyword("kb_test", "python sql", k=2)[0].id == "exact"


def test_keyword_matching_ignores_punctuation(store):
    # KB text reads "Skills: Python, SQL." - the tokens are "Skills:", "Python,", "SQL."
    store.add("kb_test", ["kb_text", "plain"], ["skills: python, sql.", "skills python sql"], _x(2))
    scores = {h.id: h.score for h in Retriever(store=store).keyword("kb_test", "skills python sql", k=2)}
    assert scores["kb_text"] == scores["plain"]


def test_a_record_matching_every_query_term_outranks_one_matching_a_single_term(store):
    store.add("kb_test", ["all", "one"], ["python sql data pipeline", "sql"], _x(2))
    scores = {h.id: h.score for h in Retriever(store=store).keyword("kb_test", "python sql data", k=2)}
    assert scores["all"] > scores["one"]


def test_hybrid_is_the_deduped_union_of_both_channels_at_their_best_score(store):
    _seed(store)
    r = Retriever(store=store)
    sem = {h.id: h.score for h in r.semantic("kb_test", "python sql", k=3)}
    kw = {h.id: h.score for h in r.keyword("kb_test", "python sql", k=3)}
    hits = r.hybrid("kb_test", "python sql", k=10, fetch=3)
    assert sorted(h.id for h in hits) == sorted(set(sem) | set(kw))
    # Fused by rank (RRF, audit #4), not max(score): a share of the best possible fused score, in [0, 1].
    assert all(0.0 <= h.score <= 1.0 for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    if next(iter(sem)) == next(iter(kw)):                 # first place in both channels is the best possible score
        assert hits[0].score == 1.0


def test_hybrid_never_leaks_a_filtered_out_type_from_either_channel(store):
    _seed(store)
    hits = Retriever(store=store).hybrid("kb_test", "python sql data", k=10, fetch=10,
                                         where={"type": {"$in": ["skill", "gap_answer"]}})
    assert hits and {h.metadata["type"] for h in hits} <= {"skill", "gap_answer"}


def test_hybrid_hands_the_reranker_the_merged_set_once(store):
    _seed(store)
    spy = SpyReranker()
    hits = Retriever(store=store, reranker=spy).hybrid("kb_test", "python sql", k=2, fetch=4)
    ((query, seen, top_k),) = spy.calls
    assert (query, top_k) == ("python sql", 2)
    assert len(seen) == len(set(seen))                                    # deduped before the expensive stage
    assert len(hits) == 2 and {h.id for h in hits} <= set(seen)


# =============================================================================
# backend/routes/kb.py - /api/search and the KB browser, called as functions
# =============================================================================
@pytest.fixture
def search_store(store, monkeypatch):
    monkeypatch.setattr(kb_routes, "get_vector_store", lambda: store)
    return store


def test_the_search_route_returns_the_store_hits_in_its_wire_shape(search_store):
    _seed(search_store, collection="profile")             # /search only reads the allowlisted collections (#45)
    body = kb_routes.search(kb_routes.SearchRequest(query="python sql", collection="profile", k=3), ADMIN)
    hits = search_store.query("profile", "python sql", k=3)
    assert body == {"query": "python sql", "collection": "profile",
                    "hits": [{"id": h.id, "text": h.document, "metadata": h.metadata, "score": h.score} for h in hits]}
    json.dumps(body)                                                      # goes out as JSON


@pytest.mark.parametrize("k", [0, -3])
def test_search_refuses_a_non_positive_k_before_the_store(search_store, k):
    _seed(search_store, collection="profile")         # built, so the request reaches the k check, not the read door
    with pytest.raises((ValidationError, HTTPException)):
        kb_routes.search(kb_routes.SearchRequest(query="python", collection="profile", k=k), ADMIN)


@pytest.fixture
def kb_tree(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    files = {
        "profile/projects.json": [{"project_id": "a"}, {"project_id": "b"}, {"project_id": "c"}],
        "do_not_claim/do_not_claim.json": {"_comment": "x", "forbidden_claims": [{"claim": "Worked at Google"}]},
        "auth/tokens.json": [{"token": "SECRET-TOKEN"}],
    }
    for rel, data in files.items():
        (kb / rel).parent.mkdir(parents=True, exist_ok=True)
        (kb / rel).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(kb_routes, "KB_DIR", kb)
    return kb


def test_the_kb_browser_reads_a_store_file_and_caps_it(kb_tree):
    assert kb_routes.kb_file("profile", "projects", ADMIN, limit=2) == {
        "file": "projects", "total": 3, "records": [{"project_id": "a"}, {"project_id": "b"}]}
    assert kb_routes.kb_file("claim_boundaries", "do_not_claim", ADMIN)["records"] == [{"claim": "Worked at Google"}]   # the wrapper's list (#51)


@pytest.mark.parametrize("store_name, file", [
    ("profile", "../auth/tokens"),
    ("profile", "../../kb/auth/tokens"),
    ("claim_boundaries", "../auth/tokens"),
    ("profile", "missing"),
    ("auth", "tokens"),
    ("chroma", "chroma"),
])
def test_the_kb_browser_never_serves_outside_its_four_stores(kb_tree, store_name, file):
    with pytest.raises(HTTPException) as exc:
        kb_routes.kb_file(store_name, file, ADMIN)
    assert exc.value.status_code == 404


def test_the_kb_overview_counts_records_and_vectors(kb_tree, tmp_path, monkeypatch):
    disk = VectorStore(embedder=FakeEmbedder(), persist_dir=tmp_path / "chroma")
    disk.add("profile", ["a", "b"], ["x", "y"], _x(2))
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "chroma")
    body = kb_routes.kb_overview(ADMIN)
    assert set(body["stores"]) == set(kb_routes.STORES)
    assert body["stores"]["profile"] == [{"file": "projects", "records": 3}]
    assert body["vectors"] == {"profile": 2}
    assert "SECRET-TOKEN" not in json.dumps(body)


def test_the_kb_browser_exposes_the_four_stores_and_never_the_private_folders():
    assert set(kb_routes.STORES.values()) == {"profile", "documents", "do_not_claim", "learning"}
    for folder in kb_routes.STORES.values():
        assert (config.KB_DIR / folder).is_dir()


# =============================================================================
# vectordb/lookup.py - records by id, no embedding model
# =============================================================================
@pytest.fixture
def disk_index(tmp_path, monkeypatch):
    path = tmp_path / "chroma"
    monkeypatch.setattr(config, "VECTORDB_DIR", path)
    return VectorStore(embedder=FakeEmbedder(), persist_dir=path)


def test_profile_blocks_follow_the_ids_order_dedupe_and_skip_unknowns(disk_index):
    disk_index.add("profile", ["skill:s1", "project:p1"], ["python pandas", "etl pipeline"],
                   [{"type": "skill", "source_id": "s1"}, {"type": "project", "source_id": "p1"}])
    assert lookup.profile_blocks(["project:p1", "nope", "skill:s1", "project:p1"]) == [
        ProfileBlock(source_id="project:p1", content="etl pipeline", category="project", skills=[]),
        ProfileBlock(source_id="skill:s1", content="python pandas", category="skill", skills=[]),
    ]


def test_profile_blocks_are_shaped_like_the_profile_agents_evidence(disk_index):
    # agents/profile.py turns each retrieved hit into
    # ProfileBlock(source_id=h.id, content=h.document, category=h.metadata["type"], skills=[]).
    _seed(disk_index, collection="profile")
    hits = disk_index.query("profile", "python sql", k=4)
    assert lookup.profile_blocks([h.id for h in hits]) == [
        ProfileBlock(source_id=h.id, content=h.document, category=h.metadata.get("type"), skills=[]) for h in hits]


def test_profile_blocks_with_no_ids_never_opens_the_index(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "nowhere")
    assert lookup.profile_blocks([]) == []
    assert not (tmp_path / "nowhere").exists()


def test_profile_blocks_without_a_profile_collection_says_how_to_fix_it(disk_index):
    disk_index.add("documents", ["d"], ["x"], _x(1))
    with pytest.raises(RuntimeError, match="build_vectordb"):
        lookup.profile_blocks(["skill:s1"])


def test_what_ingest_indexes_lookup_reads_back_verbatim(disk_index, tmp_path):
    kb = _mini_kb(tmp_path / "kb")
    ingest.build(disk_index, kb_dir=kb)
    rec = json.loads((kb / "profile" / "projects.json").read_text(encoding="utf-8"))[0]
    (block,) = lookup.profile_blocks([f"project:{rec['project_id']}"])
    assert (block.content, block.category) == (ingest._project_text(rec), "project")


# =============================================================================
# vectordb/ingest.py + build_vectordb.py - KB JSON -> collections
# =============================================================================
def test_sources_read_only_the_three_vector_stores():
    assert {rel.split("/")[0] for rel, *_ in ingest.SOURCES} == {"profile", "documents", "learning"}
    assert set(TYPE_COLLECTION.values()) == set(ingest.COLLECTIONS)
    types = [rtype for _, _, rtype, *_ in ingest.SOURCES]
    assert len(types) == len(set(types))                                  # one type, one source


def test_build_counts_types_and_namespaces_ids_by_type(store, tmp_path):
    counts = ingest.build(store, kb_dir=_mini_kb(tmp_path / "kb"))
    assert counts == {"project": 2, "skill": 1, "education": 1, "cv_example": 1, "agent_learning": 1}
    assert _ids(store, "profile") == {"project:p1", "project:p2", "skill:p1", "education:e1"}   # same raw id twice
    assert (_ids(store, "documents"), _ids(store, "learning")) == ({"cv_example:cv1"}, {"agent_learning:l1"})


def test_build_metadata_is_scalar_typed_and_drops_empty_fields(store, tmp_path):
    ingest.build(store, kb_dir=_mini_kb(tmp_path / "kb"))
    got = store._collection("profile").get(ids=["project:p2", "education:e1"])
    metas = dict(zip(got["ids"], got["metadatas"]))
    assert metas["project:p2"] == {"type": "project", "source_id": "p2"}                     # empty title dropped
    assert metas["education:e1"] == {"type": "education", "source_id": "e1", "degree": "MSc", "major": "Data Science"}


def test_the_do_not_claim_list_never_enters_any_collection(store, tmp_path):
    ingest.build(store, kb_dir=_mini_kb(tmp_path / "kb"))
    for col in ingest.COLLECTIONS:
        got = store._collection(col).get()
        assert not any(i.startswith("dnc_") or ":dnc_" in i for i in got["ids"])
        assert not any("PhD in Computer Science" in d for d in got["documents"])


def test_a_rebuild_without_reset_is_idempotent(store, tmp_path):
    kb = _mini_kb(tmp_path / "kb")
    first = ingest.build(store, kb_dir=kb)
    sizes = {c: store.count(c) for c in ingest.COLLECTIONS}
    assert ingest.build(store, kb_dir=kb, reset=False) == first
    assert {c: store.count(c) for c in ingest.COLLECTIONS} == sizes


def test_only_a_reset_drops_a_record_removed_from_the_kb(store, tmp_path):
    kb = _mini_kb(tmp_path / "kb")
    ingest.build(store, kb_dir=kb)
    path = kb / "profile" / "projects.json"
    path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8"))[:1]), encoding="utf-8")
    ingest.build(store, kb_dir=kb, reset=False)
    assert "project:p2" in _ids(store, "profile")                          # an upsert never deletes
    ingest.build(store, kb_dir=kb)
    assert "project:p2" not in _ids(store, "profile")


def test_build_resets_only_its_own_collections(store, tmp_path):
    store.add("pdf_documents", ["cv:0"], ["chunk"], _x(1))
    ingest.build(store, kb_dir=_mini_kb(tmp_path / "kb"))
    assert store.count("pdf_documents") == 1


def test_a_record_without_its_id_names_the_file_and_the_field(store, tmp_path):
    kb = _mini_kb(tmp_path / "kb")
    (kb / "profile" / "skills.json").write_text(json.dumps([{"name": "Rust"}]), encoding="utf-8")
    with pytest.raises(KeyError, match="skills.json.*skill_id"):
        ingest.build(store, kb_dir=kb)


def test_build_index_reports_counts_and_collection_sizes_that_agree(store, tmp_path):
    counts, sizes = build_index(store, kb_dir=_mini_kb(tmp_path / "kb"))
    assert set(sizes) == set(ingest.COLLECTIONS)
    for col in ingest.COLLECTIONS:
        assert sizes[col] == sum(n for t, n in counts.items() if TYPE_COLLECTION[t] == col)


def test_a_string_where_a_list_is_expected_is_kept_whole():
    text = ingest._project_text({"basic_info": {"title": "T", "domain": "DeFi"}, "skills_demonstrated": "Python"})
    assert "DeFi" in text and "Python" in text


def test_a_build_that_fails_leaves_the_previous_index_intact(store, tmp_path):
    kb = _mini_kb(tmp_path / "kb")
    ingest.build(store, kb_dir=kb)
    before = _ids(store, "profile")
    (kb / "profile" / "skills.json").write_text(json.dumps([{"name": "Rust"}]), encoding="utf-8")
    with pytest.raises(KeyError):
        ingest.build(store, kb_dir=kb)
    assert _ids(store, "profile") == before


def test_a_rebuild_keeps_the_users_own_entries_retrievable(store, tmp_path, monkeypatch):
    kb = _mini_kb(tmp_path / "kb")
    monkeypatch.setattr(profile_store, "MANUAL_ENTRIES", kb / "profile" / "manual_entries.json")
    ingest.build(store, kb_dir=kb)
    (rec,) = profile_store.save_gap_answers([{"requirement": "SQL", "content": "Queried 40M-row tables."}], store=store)
    assert f"gap_answer:{rec['id']}" in _ids(store, "profile")
    ingest.build(store, kb_dir=kb)                     # what scripts/build_vectordb.py does: reset=True
    assert f"gap_answer:{rec['id']}" in _ids(store, "profile")


# =============================================================================
# Record types: every writer and every reader of the profile collection agree
# =============================================================================
def _profile_quotas() -> list[tuple[list[str], int]]:
    """agents/profile.QUOTAS, read from the source: importing the module loads the reranker."""
    tree = ast.parse((ROOT / "agents" / "profile.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "QUOTAS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("QUOTAS not found in agents/profile.py")


def _profile_writers() -> dict[str, set[str]]:
    from backend.routes.profile import SECTION_TYPES
    return {"ingest": PROFILE_TYPES, "build_profile": set(SECTION_TYPES.values()),
            "gap_answers": {profile_store.RECORD_TYPE}}


def test_every_profile_quota_retrieves_a_type_some_writer_indexes():
    written = set().union(*_profile_writers().values())
    for types, n in _profile_quotas():
        assert n >= 1 and types and set(types) <= written, types           # a dead quota is recall that isn't there


def test_build_profile_and_cv_sections_write_only_types_ingest_knows():
    from backend.routes.profile import SECTION_TYPES
    assert set(SECTION_TYPES.values()) <= PROFILE_TYPES
    assert {t for t in SECTION_TO_KB_TYPE.values() if t} <= PROFILE_TYPES
    assert set(SECTION_TO_KB_TYPE) == set(SectionType)                     # every CV section is mapped, maybe to None


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #64: education and extracurricular are indexed "
                                       "but no Profile quota retrieves them")
def test_every_indexed_profile_type_is_retrievable_by_the_profile_agent():
    quota_types = {t for types, _ in _profile_quotas() for t in types}
    for writer, types in _profile_writers().items():
        assert types <= quota_types, (writer, sorted(types - quota_types))


# =============================================================================
# knowledge_base/ - the real fixtures, read-only
# =============================================================================
NAME_OF = {   # the field a record is known by: its embedded text must carry it
    "project": lambda r: r["basic_info"]["title"],
    "work_experience": lambda r: r["company"],
    "education": lambda r: r["institution"],
    "skill": lambda r: r["name"],
    "coursework": lambda r: r["course_name"],
    "achievement": lambda r: r["title"],
    "extracurricular": lambda r: r["activity_name"],
    "cv_example": lambda r: r["target_role"],
    "cover_letter_example": lambda r: r["target_role"],
    "agent_learning": lambda r: (r.get("embedding_text") or r["lesson"]["summary"])[:30],
}


@pytest.fixture(scope="module")
def real_kb() -> dict[str, list]:
    return {rel: json.loads((config.KB_DIR / rel).read_text(encoding="utf-8"))
            for rel, *_ in ingest.SOURCES if (config.KB_DIR / rel).is_file()}


def test_every_source_file_exists_in_the_real_kb():
    # ingest skips a missing file silently: a whole record type would vanish from retrieval.
    assert [rel for rel, *_ in ingest.SOURCES if not (config.KB_DIR / rel).is_file()] == []
    assert set(NAME_OF) == ALL_TYPES


@pytest.mark.parametrize("source", ingest.SOURCES, ids=lambda s: s[2])
def test_every_real_record_ingests_cleanly(real_kb, source):
    rel, id_field, rtype, _, text_fn, meta_fn = source
    records = real_kb[rel]
    assert isinstance(records, list) and records
    ids = [r[id_field] for r in records]
    assert len(ids) == len(set(ids)), "duplicate ids collapse into one vector"
    for r in records:
        text = text_fn(r)
        assert len(text) > 40 and NAME_OF[rtype](r) in text, r[id_field]
        assert all(isinstance(v, (str, int, float, bool)) for v in meta_fn(r).values()), r[id_field]


def test_the_real_kb_builds_with_no_collapsed_ids(store):
    counts, sizes = build_index(store)
    assert set(counts) - RUNTIME_TYPES == ALL_TYPES
    for col in ingest.COLLECTIONS:
        assert sizes[col] == sum(n for t, n in counts.items() if TYPE_COLLECTION.get(t, "profile") == col)
    for col in ingest.COLLECTIONS:                                         # nothing but declared types got in
        assert {m["type"] for m in store._collection(col).get()["metadatas"]} <= ALL_TYPES | RUNTIME_TYPES


def _check_links(kb: Path) -> None:
    load = lambda rel: json.loads((kb / rel).read_text(encoding="utf-8"))   # noqa: E731
    projects = load("profile/projects.json")
    pids, titles = {p["project_id"] for p in projects}, {p["basic_info"]["title"] for p in projects}
    eids = {w["experience_id"] for w in load("profile/work_experience.json")}
    for s in load("profile/skills.json"):
        assert set(s["projects_used_in"]) <= pids and set(s["work_experience_used_in"]) <= eids, s["skill_id"]
    for a in load("profile/achievements.json"):
        assert set(a["related_projects"]) <= pids, a["achievement_id"]
    for w in load("profile/work_experience.json"):
        assert set(w["projects"]) <= titles, w["experience_id"]


def test_every_cross_reference_in_the_real_kb_resolves():
    _check_links(config.KB_DIR)


def test_the_real_claims_list_is_well_formed_and_its_txt_is_current():
    data = json.loads((config.KB_DIR / "do_not_claim" / "do_not_claim.json").read_text(encoding="utf-8"))
    claims = data["forbidden_claims"]
    ids = [c["id"] for c in claims]
    assert claims and len(ids) == len(set(ids))
    for c in claims:
        assert c["claim"].strip()
        assert isinstance(c.get("match", []), list) and all(isinstance(m, str) and m.strip() for m in c.get("match", []))
    txt = (config.KB_DIR / "do_not_claim" / "do_not_claim.txt").read_text(encoding="utf-8").splitlines()
    assert txt == [c["claim"] for c in claims]                             # prep's output is not stale


def test_agent_prompt_files_one_per_agent_with_unique_prefixed_ids():
    folder = config.KB_DIR / "agent_prompts"
    assert sorted(p.stem for p in folder.glob("*.json")) == sorted(generate_kb_data.AGENT_ROSTER)
    for agent in generate_kb_data.AGENT_ROSTER:
        ids = [e["example_id"] for e in json.loads((folder / f"{agent}.json").read_text(encoding="utf-8"))]
        assert ids and len(ids) == len(set(ids)) and all(i.startswith(f"{agent}_prompt_") for i in ids)


def test_every_tracked_kb_json_file_parses():
    for path in config.KB_DIR.rglob("*.json"):
        if {"chroma", "auth", "input"} & set(path.relative_to(config.KB_DIR).parts):
            continue                                                       # runtime / private, not fixtures
        json.loads(path.read_text(encoding="utf-8"))


# =============================================================================
# utils/generate_kb_data.py + utils/setup_kb_prep.py - making the KB
# =============================================================================
def test_generation_is_reproducible_and_seed_sensitive(tmp_path):
    a = generate_kb_data.generate(n=4, small=2, agent_n=2, seed=7, kb_dir=tmp_path / "a")
    generate_kb_data.generate(n=4, small=2, agent_n=2, seed=7, kb_dir=tmp_path / "b")
    generate_kb_data.generate(n=4, small=2, agent_n=2, seed=8, kb_dir=tmp_path / "c")
    for path in a:
        twin = tmp_path / "b" / path.relative_to(tmp_path / "a")
        assert path.read_bytes() == twin.read_bytes(), path.name
    projects = Path("profile") / "projects.json"
    assert (tmp_path / "a" / projects).read_bytes() != (tmp_path / "c" / projects).read_bytes()


def test_generated_data_ingests_with_every_link_resolved(store, tmp_path):
    kb = tmp_path / "kb"
    generate_kb_data.generate(n=4, small=2, agent_n=2, seed=3, kb_dir=kb)
    counts = ingest.build(store, kb_dir=kb)
    assert counts == {t: (2 if t in SMALL_TYPES else 4) for t in ALL_TYPES}
    assert store.count("profile") == sum(counts[t] for t in PROFILE_TYPES)   # no id collapsed
    _check_links(kb)


def test_generation_works_for_every_n_it_accepts(tmp_path):
    for seed in range(10):                                                 # generate() clamps n to >= 1
        generate_kb_data.generate(n=1, small=1, agent_n=1, seed=seed, kb_dir=tmp_path / str(seed))


@pytest.fixture
def prep_kb(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    generate_kb_data.generate(n=4, small=2, agent_n=1, seed=5, kb_dir=kb)
    monkeypatch.setattr(setup_kb_prep, "KB", kb)
    monkeypatch.setattr(config, "KB_LEARNING_DIR", kb / "learning")
    return kb


def test_prep_writes_the_claims_list_and_routes_learning_to_agent_folders(prep_kb):
    n, folders = setup_kb_prep.prep()
    claims = [c["claim"] for c in
              json.loads((prep_kb / "do_not_claim" / "do_not_claim.json").read_text(encoding="utf-8"))["forbidden_claims"]]
    assert n == len(claims)
    assert (prep_kb / "do_not_claim" / "do_not_claim.txt").read_text(encoding="utf-8").splitlines() == claims
    assert set(folders) == set(setup_kb_prep.AGENT_FOLDERS)
    learnings = json.loads((prep_kb / "learning" / "agent_learnings.json").read_text(encoding="utf-8"))
    routed = 0
    for folder in setup_kb_prep.AGENT_FOLDERS:
        loaded = learning_store.load_learning(folder)                      # prep writes what the store reads
        assert all(setup_kb_prep.AGENT_MAP[e["agent_name"]] == folder for e in loaded["exemplars"])
        assert folders[folder] == (len(loaded["exemplars"]), len(loaded["corrections"]))
        assert (prep_kb / "learning" / folder / "feedback.jsonl").is_file()
        routed += len(loaded["exemplars"])
    assert routed == sum(1 for r in learnings if r.get("agent_name") in setup_kb_prep.AGENT_MAP)


def test_prep_is_repeatable_and_keeps_the_feedback_runs_have_written(prep_kb):
    first = setup_kb_prep.prep()
    learning_store.append_feedback("critic", {"decision": "approve"})
    assert setup_kb_prep.prep() == first
    assert len(learning_store.load_learning("critic")["feedback"]) == 1


def test_prep_keeps_the_corrections_runs_have_written(prep_kb):
    setup_kb_prep.prep()
    learning_store.save_correction("document", "old line", "new line", "edited at gate 4")
    setup_kb_prep.prep()
    assert any(c.get("after") == "new line" for c in learning_store.load_learning("document")["corrections"])


# =============================================================================
# vectordb/pdf_ingest.py + utils/cv_handling/cv_ingest.py - the PDF sandbox
# =============================================================================
def test_chunks_respect_the_size_and_lose_no_words():
    words = [f"w{i}" for i in range(600)]
    text = "\n\n".join(" ".join(words[i:i + 30]) for i in range(0, 600, 30))
    chunks = pdf_ingest.chunk_text(text)
    assert len(chunks) > 1 and all(0 < len(c) <= 400 for c in chunks)
    assert set(" ".join(chunks).split()) == set(words)


@pytest.mark.parametrize("text", ["", "   \n\n  "])
def test_an_empty_text_makes_no_chunks(text):
    assert pdf_ingest.chunk_text(text) == []


@pytest.fixture
def pdfs(tmp_path, monkeypatch):
    folder = tmp_path / "pdfs"
    folder.mkdir()
    texts = {"b_cv.pdf": "python " * 200, "a_cv.pdf": "short cv text", "scan.pdf": "", "notes.txt": "never read"}
    for name in texts:
        (folder / name).write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(pdf_ingest, "extract_text", lambda path: texts[path.name])
    return folder


def test_build_from_folder_indexes_every_chunk_traceably(store, pdfs):
    counts = pdf_ingest.build_from_folder(store, pdfs)
    assert list(counts) == ["a_cv.pdf", "b_cv.pdf", "scan.pdf"]            # sorted, *.pdf only
    assert counts["a_cv.pdf"] == 1 and counts["b_cv.pdf"] > 1 and counts["scan.pdf"] == 0
    assert store.count("pdf_documents") == sum(counts.values())
    got = store._collection("pdf_documents").get()
    for id_, meta in zip(got["ids"], got["metadatas"]):
        stem, i = id_.rsplit(":", 1)
        assert meta == {"type": "pdf_chunk", "source_file": f"{stem}.pdf", "chunk_index": int(i)}


def test_only_a_reset_drops_stale_trailing_chunks(store, pdfs, monkeypatch):
    pdf_ingest.build_from_folder(store, pdfs)
    monkeypatch.setattr(pdf_ingest, "extract_text", lambda path: "short")
    pdf_ingest.build_from_folder(store, pdfs, reset=False)
    assert "b_cv:1" in _ids(store, "pdf_documents")                       # the documented caveat
    pdf_ingest.build_from_folder(store, pdfs)
    assert _ids(store, "pdf_documents") == {"a_cv:0", "b_cv:0", "scan:0"}


@pytest.mark.skipif(not config.CV_DEFAULT_PATH.is_file(), reason="no sample CV PDF on this machine (git-ignored)")
def test_the_sample_cv_has_a_text_layer_that_chunks():
    text = pdf_ingest.extract_text(config.CV_DEFAULT_PATH)
    chunks = pdf_ingest.chunk_text(text)
    assert len(text.strip()) > 200 and chunks and all(len(c) <= 400 for c in chunks)


def test_the_sandbox_inspectors_never_create_an_index(tmp_path):
    from utils.cv_handling import cv_ingest
    nowhere = tmp_path / "nowhere"
    assert cv_ingest.ingested_pdfs(nowhere) == [] and cv_ingest.indexed_chunks(nowhere) == 0
    assert cv_ingest.ingest_cvs(tmp_path / "no_input", tmp_path / "idx") == {}    # no PDFs: index untouched
    assert not nowhere.exists() and not (tmp_path / "idx").exists()


def test_sandbox_ingest_then_inspect_round_trips(tmp_path, pdfs, monkeypatch):
    from utils.cv_handling import cv_ingest
    import vectordb.store as store_mod

    real = store_mod.VectorStore
    monkeypatch.setattr(store_mod, "VectorStore",
                        lambda persist_dir=None, **kw: real(embedder=FakeEmbedder(), persist_dir=persist_dir))
    counts = cv_ingest.ingest_cvs(pdfs, tmp_path / "idx")
    assert cv_ingest.ingested_pdfs(tmp_path / "idx") == ["a_cv.pdf", "b_cv.pdf"]   # scan.pdf has no chunks
    assert cv_ingest.indexed_chunks(tmp_path / "idx") == sum(counts.values())


def test_importing_vectordb_loads_no_model_library():
    code = ("import sys, vectordb, vectordb.retriever, vectordb.lookup, vectordb.pdf_ingest; "
            "print('sentence_transformers' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=180,
                         env={**os.environ, "TRACE": "0"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "False"


# =============================================================================
# scripts/ - the KB runners and demos
# =============================================================================
def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"kb_script_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KB_SCRIPTS = ["build_vectordb", "generate_kb_data", "setup_kb_prep", "demo_vectordb", "demo_retriever",
              "demo_rerank", "ingest_pdfs_test", "match_cv_test"]


@pytest.mark.parametrize("name", KB_SCRIPTS)
def test_kb_scripts_run_nothing_on_import(name, monkeypatch):
    import vectordb.embeddings as emb_mod
    import vectordb.reranker as rr_mod
    import vectordb.store as store_mod

    def refuse(*a, **kw):
        raise AssertionError(f"scripts/{name}.py did work at import")

    monkeypatch.setattr(store_mod.VectorStore, "__init__", refuse)
    monkeypatch.setattr(emb_mod.Embedder, "__init__", refuse)
    monkeypatch.setattr(rr_mod.Reranker, "__init__", refuse)
    monkeypatch.setattr(generate_kb_data, "generate", refuse)
    monkeypatch.setattr(setup_kb_prep, "prep", refuse)
    assert callable(_load_script(name).main)


def test_build_vectordb_runner_prints_what_it_indexed(monkeypatch, capsys):
    mod = _load_script("build_vectordb")
    monkeypatch.setattr(mod, "build_index",
                        lambda: ({"project": 2, "skill": 1}, {"profile": 3, "documents": 0, "learning": 0}))
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "project" in out and "collection 'profile': 3 vectors" in out


def test_generate_runner_passes_its_flags_through(monkeypatch, capsys):
    mod = _load_script("generate_kb_data")
    seen = {}

    def fake_generate(**kw):
        seen.update(kw)
        return {ROOT / "knowledge_base" / "profile" / "projects.json": 7,
                ROOT / "knowledge_base" / "do_not_claim" / "do_not_claim.json": 1}

    monkeypatch.setattr(mod, "generate", fake_generate)
    monkeypatch.setattr(sys, "argv", ["generate_kb_data.py", "--n", "7", "--small", "3", "--agent-n", "2", "--seed", "9"])
    assert mod.main() == 0
    assert seen == {"n": 7, "small": 3, "agent_n": 2, "seed": 9}
    out = capsys.readouterr().out
    assert "7 records" in out and "1 file (curated)" in out


def test_setup_kb_prep_runner_reports_both_steps(monkeypatch, capsys):
    mod = _load_script("setup_kb_prep")
    monkeypatch.setattr(mod, "prep", lambda: (22, {"critic": (3, 4)}))
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "22 items" in out and "exemplars=3" in out


def test_ingest_pdfs_runner_exit_codes_and_paths(monkeypatch, capsys, tmp_path):
    mod = _load_script("ingest_pdfs_test")
    calls = []
    monkeypatch.setattr(sys, "argv", ["ingest_pdfs_test.py", "--input", str(tmp_path / "in"), "--index", str(tmp_path / "idx")])
    monkeypatch.setattr(mod, "ingest_cvs", lambda inp, idx: calls.append((inp, idx)) or {})
    assert mod.main() == 1                                                 # no PDFs
    assert calls == [(tmp_path / "in", tmp_path / "idx")]
    monkeypatch.setattr(mod, "ingest_cvs", lambda inp, idx: {"cv.pdf": 4})
    monkeypatch.setattr(mod, "indexed_chunks", lambda idx: 4)
    assert mod.main() == 0
    assert "total chunks indexed: 4" in capsys.readouterr().out


def test_match_cv_runner_exit_codes(monkeypatch, tmp_path):
    mod = _load_script("match_cv_test")
    monkeypatch.setattr(sys, "argv", ["match_cv_test.py", "--out", str(tmp_path / "out")])
    monkeypatch.setattr(mod, "resolve_pdfs", lambda pdf, inp, idx: [])
    assert mod.main() == 1                                                 # nothing to match
    monkeypatch.setattr(mod, "resolve_pdfs", lambda pdf, inp, idx: [tmp_path / "cv.pdf"])
    monkeypatch.setattr(mod, "match_cvs", lambda pdfs, **kw: None)
    assert mod.main() == 1                                                 # the profile index is unusable
    monkeypatch.setattr(mod, "match_cvs", lambda pdfs, **kw: {})
    assert mod.main() == 0


@pytest.mark.parametrize("name", ["demo_vectordb", "demo_retriever", "demo_rerank"])
def test_demos_build_an_empty_index_once_then_run(name, store, monkeypatch, capsys):
    mod = _load_script(name)
    monkeypatch.setattr(mod, "VectorStore", lambda *a, **kw: store)
    if hasattr(mod, "Reranker"):
        monkeypatch.setattr(mod, "Reranker", StubReranker)
    builds = []
    real_build = mod.build
    monkeypatch.setattr(mod, "build", lambda s: builds.append(s) or real_build(s))
    assert mod.main() == 0
    assert mod.main() == 0
    assert builds == [store]                                               # built once, never rebuilt
    assert "query" in capsys.readouterr().out


# =============================================================================
# utils/generate_kb_data.py in depth - the synthetic KB generator. Its helpers,
# every record generator's ids, schema and value domains, the agent prompt
# examples, the curated do-not-claim list, reproducibility across processes,
# and the documented generate -> prep -> build_index pipeline into an index.
# Everything is written under tmp_path; the runner is only ever patched.
# =============================================================================
G = generate_kb_data


@pytest.fixture
def rng():
    """The generator draws from the process-wide `random`: seed it, and put the
    state back afterwards so no other test inherits it."""
    state = random.getstate()
    random.seed(1234)
    yield random
    random.setstate(state)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """One synthetic KB (n=12, small=6, agent_n=4, seed=11), written once."""
    state = random.getstate()
    kb = tmp_path_factory.mktemp("gen_kb")
    written = G.generate(n=12, small=6, agent_n=4, seed=11, kb_dir=kb)
    random.setstate(state)
    return SimpleNamespace(kb=kb, written=written,
                           load=lambda rel: json.loads((kb / rel).read_text(encoding="utf-8")))


# --- helpers ------------------------------------------------------------------
def test_some_draws_distinct_items_within_its_bounds(rng):
    pool = list("abcdefgh")
    for lo, hi in [(0, 3), (2, 5), (3, 20), (8, 8)]:
        for _ in range(50):
            got = G.some(pool, lo, hi)
            assert lo <= len(got) <= min(hi, len(pool)) and len(set(got)) == len(got) and set(got) <= set(pool)


def test_date_span_is_ordered_capped_and_well_formed(rng):
    month = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
    for lo, hi, present in [(6, 40, True), (36, 60, False), (3, 30, True), (4, 40, True)]:
        presents = 0
        for _ in range(400):
            start, end = G.date_span(lo, hi, allow_present=present)
            assert month.fullmatch(start) and 2015 <= int(start[:4]) <= 2023
            if end == "Present":
                presents += 1
                continue
            assert month.fullmatch(end) and start < end and int(end[:4]) <= 2025
        assert (presents > 0) == present                                  # ~15% of draws when allowed, else never


def test_improve_pair_always_improves_within_bounds(rng):
    for _ in range(500):
        a, b = G.improve_pair()
        assert 0.55 <= a <= 0.78 and a < b <= 0.99


def test_the_small_helpers_stay_in_their_ranges(rng):
    for _ in range(300):
        assert 8 <= G.pct() <= 92
        assert re.fullmatch(r"\d\.\dM|\d{2,3}K|\d{1,2}M|\d{3,4}", G.big_num())
        assert re.fullmatch(r"20(1[7-9]|2[0-5])-(0[1-9]|1[0-2])", G.ym(2017, 2025))
        ts = G.iso_ts()
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ts) and "2024-01-01" <= ts[:10] <= "2025-06-24"


@pytest.mark.parametrize("text, slug", [
    ("Aave Risk Monitor", "aave_risk_monitor"), ("Cross-chain DEX", "cross_chain_dex"), ("  NFT Market!", "nft_market"),
])
def test_slug(text, slug):
    assert G.slug(text) == slug


def test_resume_bullets_are_five_sentences_each_opening_with_its_own_verb(rng):
    for _ in range(50):
        bullets = G.resume_bullets("DeFi", ["Docker"], "SQL")
        verbs = [b.split()[0] for b in bullets]
        assert len(bullets) == 5 and all(b.endswith(".") for b in bullets)
        assert len(set(verbs)) == 5 and set(verbs) <= set(G.ACTION_WORDS)  # "unique action verb per line"


def test_qa_returns_distinct_answered_questions(rng):
    for n in (1, 3, 5, 9):
        pairs = G.qa(n, "the Churn Model")
        assert len(pairs) == min(n, 5)
        assert len({p["question"] for p in pairs}) == len(pairs) and all(p["answer"].strip() for p in pairs)


# --- record generators: ids, schema, value domains ----------------------------
ID_FORMATS = {
    "profile/projects.json": ("project_id", r"[a-z0-9_]+_\d{3}"),
    "profile/work_experience.json": ("experience_id", r"exp_\d{3}"),
    "profile/education.json": ("education_id", r"edu_\d{3}"),
    "profile/skills.json": ("skill_id", r"skill_\d{3}"),
    "profile/coursework.json": ("course_id", r"course_\d{3}"),
    "profile/achievements.json": ("achievement_id", r"ach_\d{3}"),
    "profile/extracurriculars.json": ("activity_id", r"act_\d{3}"),
    "documents/cv_examples.json": ("example_id", r"cv_\d{3}"),
    "documents/cover_letter_examples.json": ("example_id", r"cl_\d{3}"),
    "learning/correction_records.json": ("correction_id", r"corr_\d{3}"),
    "learning/agent_learnings.json": ("learning_id", r"learn_\d{3}"),
}


@pytest.mark.parametrize("rel", sorted(ID_FORMATS))
def test_every_record_file_has_n_records_with_sequential_ids(generated, rel):
    id_field, pattern = ID_FORMATS[rel]
    records = generated.load(rel)
    expected = 6 if rel.split("/")[1] in ("education.json", "coursework.json", "extracurriculars.json") else 12
    assert len(records) == expected == generated.written[generated.kb / rel]
    ids = [r[id_field] for r in records]
    assert all(re.fullmatch(pattern, i) for i in ids) and len(set(ids)) == len(ids)
    assert [int(i[-3:]) for i in ids] == list(range(expected))           # the suffix runs 000..n-1


def test_ingest_reads_the_id_field_the_generator_writes():
    for rel, id_field, *_ in ingest.SOURCES:
        assert ID_FORMATS[rel][0] == id_field, rel


def test_projects_have_unique_titles_and_ids_derived_from_them(generated):
    projects = generated.load("profile/projects.json")
    assert len({p["basic_info"]["title"] for p in projects}) == len(projects)
    for i, p in enumerate(projects):
        assert p["project_id"] == f"{G.slug(p['basic_info']['title'])}_{i:03d}"
        assert set(p["basic_info"]["domain"]) <= set(G.DOMAINS) and set(p["skills_demonstrated"]) <= set(G.SKILLS)
        assert len(p["resume_material"]["full_bullet_points"]) == 5


def test_profile_values_come_from_their_pools_and_ranges(generated):
    for w in generated.load("profile/work_experience.json"):
        assert w["company"] in G.COMPANIES and w["role"] in G.ROLES and w["employment_type"] in G.EMPLOYMENT_TYPES
        assert w["location"] in G.LOCATIONS
        assert w["end_date"] == "Present" or w["start_date"] < w["end_date"]
    for e in generated.load("profile/education.json"):
        assert e["degree"] in G.DEGREES and e["major"] in G.MAJORS and e["institution"] in G.UNIVERSITIES
        assert e["start_date"] < e["end_date"] != "Present"                # a degree is never ongoing
        assert e["cgpa"].endswith("/4.0") and 3.0 <= float(e["cgpa"].split("/")[0]) <= 4.0
    for s in generated.load("profile/skills.json"):
        assert s["proficiency"] in G.PROFICIENCY and s["category"] in G.SKILL_CATEGORIES
        assert 1 <= s["years_of_experience"] <= 8
    for c in generated.load("profile/coursework.json"):
        assert c["course_name"] in G.COURSES and c["grade"] in G.GRADES and c["type"] in G.COURSE_TYPES
        assert set(c["relevance"].values()) <= {"high", "medium", "low"}
    for a in generated.load("profile/achievements.json"):
        assert a["category"] in G.ACHIEVEMENT_CATEGORIES
        assert re.fullmatch(r"20(1[7-9]|2[0-5])-(0[1-9]|1[0-2])", a["date"])
    for x in generated.load("profile/extracurriculars.json"):
        start, end = x["duration"].split(" to ")
        assert end == "Present" or start < end


def test_document_and_learning_values_come_from_their_pools_and_ranges(generated):
    for cv in generated.load("documents/cv_examples.json"):
        assert cv["target_role"] in G.ROLES and cv["industry"] in G.INDUSTRIES and 6.5 <= cv["score"] <= 9.6
    for cl in generated.load("documents/cover_letter_examples.json"):
        assert 6.0 <= cl["score"] <= 9.5 and cl["target_role"] in cl["cover_letter"]
    for r in generated.load("learning/correction_records.json"):
        assert r["agent_name"] in G.AGENTS and r["before"] != r["after"]
    for r in generated.load("learning/agent_learnings.json"):
        assert r["agent_name"] in G.AGENTS and 3 <= r["evaluation"]["score"] <= 10
        assert r["should_reuse"] == (r["evaluation"]["score"] >= 6)          # derived from the score, never drawn
        assert 0.4 <= r["lesson"]["confidence"] <= 0.98 and 1 <= r["importance_score"] <= 10
        assert r["agent_name"] in r["embedding_text"]


class _Reads(dict):
    """A record that logs every key an ingest builder reads, nested ones included."""

    def __init__(self, data, path, log):
        super().__init__(data)
        self._path, self._log = path, log

    def _seen(self, key, value):
        self._log.add(self._path + (key,))
        return _Reads(value, self._path + (key,), self._log) if isinstance(value, dict) else value

    def get(self, key, default=None):
        return self._seen(key, super().get(key, default))

    def __getitem__(self, key):
        return self._seen(key, super().__getitem__(key))


def _read_paths(fn, record: dict) -> set[tuple]:
    log: set[tuple] = set()
    fn(_Reads(record, (), log))
    return log


def _at(record, path):
    for key in path:
        record = record.get(key) if isinstance(record, dict) else None
    return record


@pytest.mark.parametrize("source", ingest.SOURCES, ids=lambda s: s[2])
def test_every_field_ingest_reads_is_generated_and_non_empty(generated, real_kb, source):
    # Cross-layer: the builders' reads are discovered, not listed by hand, so a
    # builder that starts reading a field the generator never writes fails here
    # instead of silently embedding "Skills: ." for every record.
    rel, id_field, rtype, _, text_fn, meta_fn = source
    for record in generated.load(rel) + real_kb.get(rel, []):
        for fn in (text_fn, meta_fn):
            for path in _read_paths(fn, record):
                assert _at(record, path) not in (None, "", [], {}), (rtype, record[id_field], ".".join(path))


# --- agent prompt examples ----------------------------------------------------
def test_every_roster_agent_has_an_entry_in_every_table():
    for table in (G.AGENT_ROLE, G.AGENT_OBJECTIVES, G.AGENT_SYSTEM_BASE, G.AGENT_EMPHASIS,
                  G.AGENT_INSTRUCTIONS, G.AGENT_SUCCESS, G.AGENT_FAILURE, G.AGENT_LEARNING):
        assert set(table) == set(G.AGENT_ROSTER)
    assert set(G.SEED_TEMPLATES) <= set(G.AGENT_ROSTER) and set(G.AGENTS) == set(G.AGENT_ROSTER)


def test_every_agent_gets_n_prompt_examples_with_its_verbatim_seed_first(generated):
    folder = generated.kb / "agent_prompts"
    assert sorted(p.stem for p in folder.glob("*.json")) == sorted(G.AGENT_ROSTER)
    common = {"example_id", "agent_name", "role", "objective", "prompt_template",
              "success_patterns", "failure_patterns", "learning_rules"}
    for agent in G.AGENT_ROSTER:
        examples = json.loads((folder / f"{agent}.json").read_text(encoding="utf-8"))
        assert [e["example_id"] for e in examples] == [f"{agent}_prompt_{i:03d}" for i in range(4)]
        assert all(e["agent_name"] == agent and common <= set(e) for e in examples), agent
        seeded = agent in G.SEED_TEMPLATES
        if seeded:
            assert {k: v for k, v in examples[0].items() if k != "example_id"} == G.SEED_TEMPLATES[agent]
        for e in examples[1 if seeded else 0:]:
            shots = e["prompt_template"]["few_shot_examples"]
            assert 1 <= len(shots) <= 3 and all(s["input"].strip() and s["output"].strip() for s in shots)
            assert e["prompt_template"]["system"].startswith(G.AGENT_SYSTEM_BASE[agent])
            assert e["role"] == G.AGENT_ROLE[agent]


# --- generate(): what it writes, and where ------------------------------------
def test_generate_writes_only_under_kb_dir_and_reports_every_file(generated):
    assert sorted(p for p in generated.kb.rglob("*") if p.is_file()) == sorted(generated.written)
    for path, count in generated.written.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert count == (len(data) if isinstance(data, list) else 1), path.name


def test_generate_removes_the_superseded_combined_prompt_file(tmp_path, rng):
    legacy = tmp_path / "agent_prompts" / "agent_prompt_examples.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[]", encoding="utf-8")
    G.generate(n=4, small=1, agent_n=1, seed=1, kb_dir=tmp_path)
    assert not legacy.exists()


def test_generate_clamps_small_and_agent_n_to_at_least_one(tmp_path, rng):
    written = G.generate(n=4, small=0, agent_n=-3, seed=2, kb_dir=tmp_path)
    assert written[tmp_path / "profile" / "education.json"] == 1
    assert written[tmp_path / "agent_prompts" / "critic.json"] == 1


def test_the_same_seed_writes_the_same_bytes_in_any_process(tmp_path):
    # The runner promises "same seed = same data". Two processes with different
    # hash seeds catch any set/dict-order dependence one process can't.
    code = ("import sys; from pathlib import Path; from utils.generate_kb_data import generate; "
            "generate(n=5, small=2, agent_n=2, seed=42, kb_dir=Path(sys.argv[1]))")
    for name, hashseed in (("a", "1"), ("b", "2")):
        out = subprocess.run([sys.executable, "-c", code, str(tmp_path / name)], cwd=ROOT, capture_output=True,
                             text=True, timeout=180, env={**os.environ, "PYTHONHASHSEED": hashseed, "TRACE": "0"})
        assert out.returncode == 0, out.stderr
    a = {p.relative_to(tmp_path / "a"): p.read_bytes() for p in (tmp_path / "a").rglob("*.json")}
    b = {p.relative_to(tmp_path / "b"): p.read_bytes() for p in (tmp_path / "b").rglob("*.json")}
    assert a and a == b


def test_asking_for_more_projects_than_titles_never_hangs(rng, monkeypatch):
    calls = itertools.count()
    real_pick = G.pick

    def bounded_pick(seq):                     # a hard stop, so the bug fails instead of hanging the suite
        if next(calls) > 200_000:
            raise RuntimeError("gen_projects is still drawing titles: it would never return")
        return real_pick(seq)

    monkeypatch.setattr(G, "pick", bounded_pick)
    try:
        projects = G.gen_projects(419)          # 22 subjects x 19 nouns = 418 unique titles
    except ValueError:
        return                                 # refusing loudly is a fine fix
    assert len(projects) == 419


# --- the curated do-not-claim list --------------------------------------------
def test_the_curated_claims_list_is_well_formed_and_not_random():
    data = G.gen_do_not_claim()
    claims = data["forbidden_claims"]
    assert data["version"] == 1 and "never embedded" in data["_comment"]
    assert [c["id"] for c in claims] == [f"dnc_{i:03d}" for i in range(len(claims))]
    assert len({c["claim"] for c in claims}) == len(claims)
    for c in claims:
        assert c["claim"].strip() and c["reason"].strip() and c["match_mode"] == "fuzzy"
        assert c["match"] and len(set(c["match"])) == len(c["match"]), c["id"]
        assert all(m and m == m.strip().lower() for m in c["match"]), c["id"]     # matched against lowercased text
    assert G.gen_do_not_claim() == data


def _forbidden_hits(records: list[dict]) -> list[tuple[str, str]]:
    terms = [(c["id"], m) for c in G.gen_do_not_claim()["forbidden_claims"] for m in c["match"]]
    hits = []
    for record in records:
        text = json.dumps(record, ensure_ascii=False).lower()
        hits += [(cid, m) for cid, m in terms if re.search(rf"(?<!\w){re.escape(m)}(?!\w)", text)]
    return hits


def test_the_synthetic_profile_never_matches_its_own_do_not_claim_list(rng):
    records = (G.gen_projects(60) + G.gen_work(60, ["T1", "T2", "T3"]) + G.gen_education(60)
               + G.gen_skills(60, ["p1", "p2", "p3", "p4"], ["e1", "e2", "e3"]) + G.gen_coursework(60)
               + G.gen_achievements(400, ["p1", "p2"]) + G.gen_extracurriculars(60))
    assert _forbidden_hits(records) == []


# --- the documented pipeline: generate -> prep -> build_index -----------------
def test_the_documented_pipeline_gives_a_consistent_kb_and_index(store, tmp_path, monkeypatch, rng):
    kb = tmp_path / "kb"
    written = G.generate(n=6, small=3, agent_n=2, seed=21, kb_dir=kb)
    monkeypatch.setattr(setup_kb_prep, "KB", kb)
    monkeypatch.setattr(config, "KB_LEARNING_DIR", kb / "learning")
    n_claims, folders = setup_kb_prep.prep()
    counts, sizes = build_index(store, kb_dir=kb)
    for rel, _, rtype, *_ in ingest.SOURCES:
        assert counts[rtype] == written[kb / rel], rtype                  # every generated record indexed once
    for col in ingest.COLLECTIONS:
        assert sizes[col] == sum(n for t, n in counts.items() if TYPE_COLLECTION[t] == col)
    assert n_claims == len(G.gen_do_not_claim()["forbidden_claims"])
    assert set(folders) == set(setup_kb_prep.AGENT_FOLDERS)
    indexed = {m["type"] for col in ingest.COLLECTIONS for m in store._collection(col).get()["metadatas"]}
    assert indexed == ALL_TYPES                                           # prep's files never reach the index


def test_the_same_generated_kb_builds_the_same_index(store, tmp_path, rng):
    kb = tmp_path / "kb"
    G.generate(n=5, small=2, agent_n=1, seed=8, kb_dir=kb)

    def snapshot():
        build_index(store, kb_dir=kb)
        return {col: sorted(zip(*(store._collection(col).get()[k] for k in ("ids", "documents"))))
                for col in ingest.COLLECTIONS}

    assert snapshot() == snapshot()


def test_the_generate_runner_defaults_match_the_library(monkeypatch):
    mod = _load_script("generate_kb_data")
    seen = {}
    monkeypatch.setattr(mod, "generate", lambda **kw: seen.update(kw) or {})
    monkeypatch.setattr(sys, "argv", ["generate_kb_data.py"])
    assert mod.main() == 0
    defaults = {k: v.default for k, v in inspect.signature(G.generate).parameters.items() if k != "kb_dir"}
    assert seen == defaults == {"n": 50, "small": 10, "agent_n": 50, "seed": 42}


# =============================================================================
# KB + RAG + retrieval + embeddings, second pass (2026-10-13, Instruction-test.md §5.15)
# =============================================================================
# What the earlier batches left out:
#   - the Embedder and Reranker wiring itself (normalised vectors, model names,
#     the pairs sent, plain-float output), with sentence_transformers faked;
#   - k <= 0 at the reranker, the store and the keyword channel;
#   - collection names: valid for Chroma, and the same name at every writer and reader;
#   - the index never recording which embedding model built it;
#   - a null nested field in a KB record;
#   - utils/cv_handling/cv_match.py, the CV-line matcher (hybrid search per section,
#     key matching, status grading), which no test touched: unit, integration over an
#     in-memory index, determinism, section isolation, the loader's refusal paths,
#     the known open fixes (Data Storage role file §7: M3, M4, S1, S2) pinned;
#   - opt-in real-model checks: exact names retrieve their own record first, and the
#     sample CV links every line to the right record (9/9 entries, bullets follow).
# Found: bugs_audit_fixed.md #80 (3 items).
import numpy as np

from state.state import CVNode, CVTree, LineLink, MatchStatus, NodeKind
from utils.cv_handling import cv_extract
from utils.cv_handling import cv_ingest
from utils.cv_handling import cv_match


# --- the Embedder and Reranker wiring (sentence_transformers faked) -------------------------
@pytest.fixture
def fake_st(monkeypatch):
    """A stand-in sentence_transformers module: records what each model was built with and asked."""
    seen = SimpleNamespace(models=[], encode_kwargs=[], encoded=[], pairs=[])

    class SentenceTransformer:
        def __init__(self, name):
            seen.models.append(("bi", name))

        def encode(self, texts, **kwargs):
            seen.encoded.append(list(texts))
            seen.encode_kwargs.append(kwargs)
            return np.full((len(texts), 3), 1 / math.sqrt(3), dtype=np.float32)

        def get_sentence_embedding_dimension(self):
            return 3

    class CrossEncoder:
        def __init__(self, name):
            seen.models.append(("cross", name))

        def predict(self, pairs):
            seen.pairs.append([list(p) for p in pairs])
            return np.array([0.123456, 0.9, 0.5][: len(pairs)], dtype=np.float32)

    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        SimpleNamespace(SentenceTransformer=SentenceTransformer, CrossEncoder=CrossEncoder))
    return seen


def test_the_embedder_loads_the_configured_model_and_asks_for_unit_vectors(fake_st):
    """Catches a dropped normalize_embeddings=True: every cosine score in the store would be wrong."""
    from vectordb.embeddings import Embedder

    e = Embedder()
    vectors = e.embed(("python and sql", "airflow"))
    assert fake_st.models == [("bi", config.EMBEDDING_MODEL)]
    assert fake_st.encode_kwargs == [{"normalize_embeddings": True, "convert_to_numpy": True}]
    assert fake_st.encoded == [["python and sql", "airflow"]]           # one batch, order kept
    assert isinstance(vectors, list) and all(isinstance(x, float) for v in vectors for x in v)   # Chroma wants lists
    assert e.dim == 3


def test_the_reranker_scores_query_document_pairs_in_order_as_plain_floats(fake_st):
    """Catches swapped pairs (document, query) or numpy scores leaking into Hit.rerank_score."""
    rr = Reranker()
    scores = rr.score("sql engineer", ["doc a", "doc b"])
    assert fake_st.models == [("cross", config.RERANKER_MODEL)]
    assert fake_st.pairs == [[["sql engineer", "doc a"], ["sql engineer", "doc b"]]]
    assert all(type(s) is float for s in scores)


def test_the_reranker_rounds_sorts_and_cuts_with_the_real_ordering(fake_st):
    """Catches an unsorted rerank, unrounded scores, or a top_k that is ignored."""
    hits = [_hit("a", "first"), _hit("b", "second"), _hit("c", "third")]
    ranked = Reranker().rerank("q", hits, top_k=2)
    assert [h.id for h in ranked] == ["b", "c"]
    assert [h.rerank_score for h in ranked] == [0.9, 0.5]
    assert hits[0].rerank_score == 0.1235                              # every hit is scored, rounded to 4 places


def test_constructing_the_models_happens_only_on_demand():
    """Catches a model load at import of the store, retriever or lookup modules (boot cost, #43)."""
    code = ("import sys, vectordb.store, vectordb.retriever, vectordb.lookup, vectordb.ingest, "
            "utils.cv_handling.cv_ingest; print('sentence_transformers' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                         env={**os.environ, "TRACE": "0"}, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "False"


# --- k <= 0 everywhere a k is taken ---------------------------------------------------------
def test_a_reranker_asked_for_zero_hits_returns_none():
    """Catches `ranked[:top_k] if top_k else ranked`: 0 is falsy, so 'none' becomes 'all'."""
    assert StubReranker().rerank("python", [_hit("1", "python"), _hit("2", "sql")], top_k=0) == []


def test_a_reranked_search_for_zero_hits_returns_none(store):
    """Catches k=0 reaching the reranker as top_k=0 and coming back as the whole fetched set."""
    _seed(store)
    assert store.search("kb_test", "python", k=0, fetch=5, reranker=StubReranker()) == []


def test_keyword_with_a_negative_k_returns_nothing_or_refuses(store):
    """Catches `hits[:k]` with k=-1 slicing off only the last hit."""
    _seed(store)
    try:
        hits = Retriever(store=store).keyword("kb_test", "python", k=-1)
    except ValueError:
        return
    assert hits == []


def test_hybrid_without_a_reranker_for_zero_hits_returns_none(store):
    """Catches the plain path drifting from [:k] (it is right today; the reranked path is not)."""
    _seed(store)
    assert Retriever(store=store).hybrid("kb_test", "python", k=0, fetch=5) == []


# --- collection names: valid, and one name per collection across every layer ---------------
_CHROMA_NAME = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{1,61})[a-zA-Z0-9]$")
_RETRIEVER_CALLS = {"hybrid", "semantic", "keyword", "reranked", "search"}


def _collection_literals() -> dict[str, set[str]]:
    """Every collection name written as a literal at a store or retriever call, by file."""
    found: dict[str, set[str]] = {}
    for folder in ("agents", "backend", "learning", "vectordb", "utils"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args):
                    continue
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "re":   # re.search(pattern, ...)
                    continue
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    continue
                attr, n = node.func.attr, len(node.args)
                if attr in _RETRIEVER_CALLS or (attr == "add" and n == 4) or (attr == "query" and n >= 2):
                    found.setdefault(str(path.relative_to(ROOT)), set()).add(first.value)
    return found


def test_every_collection_name_the_code_uses_is_one_chroma_accepts():
    """Catches a name like "kb" (Chroma wants 3-63 characters), found only when that path first runs."""
    names = {*ingest.COLLECTIONS, cv_match.PROFILE_COLLECTION, cv_match.BULLET_COLLECTION,
             cv_ingest.PDF_COLLECTION, lookup.PROFILE_COLLECTION,
             inspect.signature(pdf_ingest.build_from_folder).parameters["collection"].default}
    for literals in _collection_literals().values():
        names |= literals
    assert names and all(_CHROMA_NAME.match(n) and ".." not in n for n in names), sorted(names)


def test_every_writer_and_reader_names_the_profile_collection_the_same_way():
    """Catches one layer writing to (or reading from) a collection the others never touch."""
    profile_types_go_to = {col for _, _, rtype, col, _, _ in ingest.SOURCES if rtype in PROFILE_TYPES}
    assert profile_types_go_to == {"profile"}
    assert lookup.PROFILE_COLLECTION == cv_match.PROFILE_COLLECTION == "profile"
    known = {*ingest.COLLECTIONS, cv_match.BULLET_COLLECTION, cv_ingest.PDF_COLLECTION}
    literals = _collection_literals()
    assert literals.get("agents/profile.py") == {"profile"}                 # what Profile retrieves from
    assert literals.get("learning/profile_store.py") == {"profile"}         # where gap answers are indexed
    assert literals.get("backend/routes/profile.py") == {"profile"}         # where Build-Profile entries go
    stray = {f: n - known for f, n in literals.items() if n - known}
    assert stray == {}


def test_the_index_records_the_embedding_model_it_was_built_with(store, tmp_path):
    """Catches a same-dimension model swap (EMBEDDING_MODEL changed, index not rebuilt) going unnoticed."""
    ingest.build(store, kb_dir=_mini_kb(tmp_path / "kb"))
    for col in ingest.COLLECTIONS:
        assert (store._collection(col).metadata or {}).get("embedding_model") == store.embedder.model_name, col


def test_a_null_nested_field_never_crashes_the_build_unnamed(store, tmp_path):
    """Catches `r.get("basic_info", {}).get(...)` on an explicit null: an AttributeError with no file or id."""
    kb = _mini_kb(tmp_path / "kb")
    projects = kb / "profile" / "projects.json"
    records = json.loads(projects.read_text(encoding="utf-8"))
    records.append({"project_id": "p9", "basic_info": None, "problem": None, "resume_material": None})
    projects.write_text(json.dumps(records), encoding="utf-8")
    try:
        ingest.build(store, kb_dir=kb)
    except Exception as exc:                                     # refusing is fine, if it says where
        assert "projects.json" in str(exc) and "p9" in str(exc), repr(exc)
        return
    assert "project:p9" in _ids(store, "profile")


# --- the CV-line matcher: units ----------------------------------------------------------------
def _cand(id_="project:p1", rerank=0.0, exact=False, document="doc", metadata=None):
    return cv_match.Cand(id_, document, metadata or {"type": "project"}, rerank=rerank, cos=None, kw=None,
                         exact=exact)


def _cvn(node_id, kind, stype, text="", attrs=None, children=(), title=""):
    depth = {NodeKind.SECTION: 1, NodeKind.ENTRY: 2}.get(kind, 3)
    return CVNode(node_id=node_id, kind=kind, section_type=stype, depth=depth, parent_id=None,
                  text=text, title=title, attrs=attrs or {}, children=list(children))


_RANK = {MatchStatus.UNMATCHED: 0, MatchStatus.PARTIAL: 1, MatchStatus.MATCHED: 2}


@pytest.mark.parametrize("kind", list(cv_match.THRESHOLDS), ids=lambda k: k.value)
def test_the_status_never_drops_as_the_rerank_rises(kind):
    """Catches crossed thresholds or a branch out of order (tested on the order, not on the provisional numbers)."""
    match_min, partial_min = cv_match.THRESHOLDS[kind]
    assert partial_min < match_min
    scores = sorted({-1.0, 0.0, partial_min - 1e-6, partial_min, (partial_min + match_min) / 2,
                     match_min - 1e-6, match_min, 1.0, 5.0})
    seq = [_RANK[cv_match.status_for(kind, _cand(rerank=s))] for s in scores]
    assert seq == sorted(seq)
    assert cv_match.status_for(kind, _cand(rerank=match_min)) is MatchStatus.MATCHED
    assert cv_match.status_for(kind, _cand(rerank=partial_min)) is MatchStatus.PARTIAL
    assert cv_match.status_for(kind, _cand(rerank=partial_min - 1e-6)) is MatchStatus.UNMATCHED


@pytest.mark.parametrize("kind", list(cv_match.THRESHOLDS), ids=lambda k: k.value)
def test_an_exact_key_lifts_entries_and_items_and_never_lowers_anything(kind):
    """Catches C4 applied to bullets, or an exact name ever making a status worse."""
    match_min, partial_min = cv_match.THRESHOLDS[kind]
    for s in (-1.0, 0.0, partial_min, (partial_min + match_min) / 2, match_min, 1.0):
        plain = cv_match.status_for(kind, _cand(rerank=s))
        exact = cv_match.status_for(kind, _cand(rerank=s, exact=True))
        assert _RANK[exact] >= _RANK[plain], (kind, s)
        if not cv_match.KEY_PROMOTES[kind]:
            assert exact is plain, (kind, s)
    if cv_match.KEY_PROMOTES[kind]:
        assert cv_match.status_for(kind, _cand(rerank=partial_min, exact=True)) is MatchStatus.MATCHED
        assert cv_match.status_for(kind, _cand(rerank=-1.0, exact=True)) is MatchStatus.PARTIAL


def test_pick_prefers_an_exact_key_then_its_best_rerank():
    """Catches an exact-name record losing to a higher-reranked stranger (the 9/9 entry rule)."""
    top, ex_low, ex_high = _cand("a", 0.99), _cand("b", 0.30, exact=True), _cand("c", 0.40, exact=True)
    assert cv_match.pick([top, ex_high, ex_low]) == (ex_high, "exact key match")
    assert cv_match.pick([top, _cand("d", 0.5)]) == (top, "top rerank")


def test_a_bullet_stays_with_its_entrys_record_unless_clearly_beaten():
    """Catches a bullet drifting to another project's record on a near-tie (templated bullets saturate)."""
    match_min = cv_match.THRESHOLDS[NodeKind.BULLET][0]
    margin = cv_match.TIE_MARGIN
    entry = _cand("own", 0.0)
    best = _cand("other", 0.40)
    assert cv_match.pick([best, _cand("own", match_min)], entry, bullet=True)[1] == "entry's record"
    assert cv_match.pick([best, _cand("own", 0.40 - margin)], entry, bullet=True)[0].id == "own"
    assert cv_match.pick([best, _cand("own", 0.40 - margin - 0.01)], entry, bullet=True)[0].id == "other"
    assert cv_match.pick([best], None, bullet=True) == (best, "entry unmatched, whole type")
    assert cv_match.pick([best], entry, bullet=True)[0] is best                 # its record not among the candidates


@pytest.mark.parametrize("kb_type, node, metadata, document, expected", [
    ("project", _cvn("e", NodeKind.ENTRY, SectionType.PROJECTS, attrs={"title": "Aave risk-monitor!"}),
     {"title": "Aave Risk Monitor"}, "", (1.0, True)),
    ("skill", _cvn("i", NodeKind.ITEM, SectionType.SKILLS, "Python (Pandas, NumPy)"),
     {"name": "Python"}, "", (1.0, True)),
    ("work_experience", _cvn("e", NodeKind.ENTRY, SectionType.EXPERIENCE, attrs={"org": "Acme", "role": "Data Engineer"}),
     {"company": "Acme", "role": "Data Engineer"}, "", (1.0, True)),
    ("project", _cvn("e", NodeKind.ENTRY, SectionType.PROJECTS), {"title": "Aave Risk Monitor"}, "", (None, False)),
    ("education", _cvn("e", NodeKind.ENTRY, SectionType.EDUCATION, attrs={"degree": "MSc"}), {}, "", (None, False)),
    ("nonsense", _cvn("i", NodeKind.ITEM, SectionType.OTHER, "Python"), {"name": "Python"}, "", (None, False)),
], ids=["title-normalised", "skill-parenthetical", "work-both-keys", "no-attrs", "empty-metadata", "unknown-type"])
def test_key_match_compares_names_after_normalising(kb_type, node, metadata, document, expected):
    """Catches case, punctuation or a parenthetical breaking an exact name, or a score made from nothing."""
    assert cv_match.key_match(node, kb_type, document, metadata) == expected


def test_a_work_entry_is_exact_only_when_company_and_role_both_are():
    """Catches one matching field (a common job title) marking the wrong employer's record exact."""
    node = _cvn("e", NodeKind.ENTRY, SectionType.EXPERIENCE, attrs={"org": "Acme", "role": "Data Engineer"})
    score, exact = cv_match.key_match(node, "work_experience", "", {"company": "Globex", "role": "Data Engineer"})
    assert exact is False and 0 < score < 1
    half = _cvn("e", NodeKind.ENTRY, SectionType.EXPERIENCE, attrs={"role": "Data Engineer"})
    assert cv_match.key_match(half, "work_experience", "", {"company": "Acme", "role": "Data Engineer"})[1] is False


def test_an_achievement_is_scored_on_its_text_and_never_called_exact():
    """Catches an achievement title settling a match outright (titles repeat across years, M3)."""
    node = _cvn("i", NodeKind.ITEM, SectionType.ACHIEVEMENTS, "2nd place DeFi Challenge")
    score, exact = cv_match.key_match(node, "achievement", "Achievement: 2nd place DeFi Challenge (hackathon).", {})
    assert score == 1.0 and exact is False


def _matcher_tree() -> CVTree:
    P, S, C, E, H, A = (SectionType.PROJECTS, SectionType.SKILLS, SectionType.COURSEWORK, SectionType.EXPERIENCE,
                        SectionType.HEADER, SectionType.ACHIEVEMENTS)
    sections = [
        _cvn("header", NodeKind.SECTION, H, title="Jane Doe", children=[
            _cvn("header.0", NodeKind.ITEM, H, "jane@example.com")]),
        _cvn("projects", NodeKind.SECTION, P, title="Projects", children=[
            _cvn("projects.0", NodeKind.ENTRY, P, "Aave Risk Monitor | Python", attrs={"title": "Aave Risk Monitor"},
                 children=[_cvn("projects.0.b0", NodeKind.BULLET, P, "Monitored Aave positions in Python"),
                           _cvn("projects.0.b1", NodeKind.BULLET, P, "  -  ")]),
        ]),
        _cvn("skills", NodeKind.SECTION, S, title="Skills", children=[
            _cvn("skills.0", NodeKind.ENTRY, S, "Languages", children=[
                _cvn("skills.0.i0", NodeKind.ITEM, S, "Python (Pandas)"),
                _cvn("skills.0.i1", NodeKind.ITEM, S, "SQL")])]),
        _cvn("coursework", NodeKind.SECTION, C, title="Coursework", children=[
            _cvn("coursework.i0", NodeKind.ITEM, C, "Databases")]),
        _cvn("experience", NodeKind.SECTION, E, title="Experience", children=[
            _cvn("experience.0", NodeKind.ENTRY, E, "Data Engineer | Acme", attrs={"role": "Data Engineer", "org": "Acme"})]),
        _cvn("achievements", NodeKind.SECTION, A, title="Awards", children=[
            _cvn("achievements.i0", NodeKind.ITEM, A, "Dean's list")]),
    ]
    return CVTree(source_file="cv.pdf", root=CVNode(node_id="cv", kind=NodeKind.CV, section_type=SectionType.OTHER,
                                                    depth=0, children=sections))


def test_plan_jobs_lists_matchable_nodes_in_tree_order_and_skips_unmatched_sections():
    """Catches a skills group matched as a record, a bullet missed, or the header sent to retrieval."""
    jobs, skipped = cv_match.plan_jobs(_matcher_tree())
    assert [(n.node_id, t) for n, t in jobs] == [
        ("projects.0", "project"), ("projects.0.b0", "project"), ("projects.0.b1", "project"),
        ("skills.0.i0", "skill"), ("skills.0.i1", "skill"),
        ("coursework.i0", "coursework"), ("experience.0", "work_experience"),
        ("achievements.i0", "achievement")]
    assert skipped == ["header.0"]


@pytest.mark.parametrize("node, kb_type, query", [
    (_cvn("e", NodeKind.ENTRY, SectionType.EXPERIENCE, "x", {"org": "Acme", "date_range": "2023", "role": "Data Engineer"}),
     "work_experience", "Data Engineer Acme"),
    (_cvn("e", NodeKind.ENTRY, SectionType.PROJECTS, "Churn Model | XGBoost"), "project", "Churn Model | XGBoost"),
    (_cvn("i", NodeKind.ITEM, SectionType.COURSEWORK, "Databases"), "coursework", "Course: Databases"),
    (_cvn("i", NodeKind.ITEM, SectionType.EDUCATION, "Dean's list"), "education", "Dean's list"),
    (_cvn("b", NodeKind.BULLET, SectionType.PROJECTS, "Built it"), "project", "Built it"),
], ids=["entry-attrs-in-order", "entry-no-attrs", "item-prefix", "item-no-prefix", "bullet"])
def test_query_for_builds_the_search_text_each_kind_needs(node, kb_type, query):
    """Catches the date or a stray attr entering an entry query, or an item losing its type prefix."""
    assert cv_match.Matcher.query_for(node, kb_type) == query


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #50 → Data Storage role file §7 M4: skills are queried with their parenthetical")
def test_a_skill_is_queried_by_its_name_alone():
    """Catches 'Skill: Python (Pandas, NumPy, ...)' reranking poorly against the Python record."""
    node = _cvn("i", NodeKind.ITEM, SectionType.SKILLS, "Python (Pandas, NumPy)")
    assert cv_match.Matcher.query_for(node, "skill") == "Skill: Python"


def _write_kb(root: Path, files: dict) -> Path:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_collect_bullets_reads_every_bullet_field_of_known_parents_only(monkeypatch, tmp_path):
    """Catches a blank bullet indexed, an orphan record's bullets indexed, or ids that skip numbers."""
    kb = _write_kb(tmp_path / "kb", {
        "profile/projects.json": [
            {"project_id": "p1", "resume_material": {"one_line": "Built a DeFi risk monitor.",
                                                     "full_bullet_points": ["Tracked Aave loans", "   ", "Cut alerts by 30%"]}},
            {"project_id": "p_orphan", "resume_material": {"one_line": "Not in the index."}}],
        "profile/work_experience.json": [
            {"experience_id": "w1", "resume_bullets": ["Ran ETL"], "achievements": ["Saved $10k"]}],
    })
    monkeypatch.setattr(config, "KB_DIR", kb)
    ids, texts, metas = cv_match.collect_bullets({"project:p1", "work_experience:w1"})
    assert ids == ["work_experience:w1#b0", "work_experience:w1#b1",
                   "project:p1#b0", "project:p1#b1", "project:p1#b2"]
    assert texts == ["Ran ETL", "Saved $10k", "Built a DeFi risk monitor.", "Tracked Aave loans", "Cut alerts by 30%"]
    assert metas[2] == {"type": "project", "parent_id": "project:p1", "bullet_index": 0}


def test_the_matcher_tables_agree_with_what_ingest_writes(real_kb):
    """Catches a renamed id field or metadata key: bullets would never find their parent, names never match."""
    sources = {rtype: (rel, id_field, meta_fn) for rel, id_field, rtype, _, _, meta_fn in ingest.SOURCES}
    for rtype, rel, id_field, paths in cv_match.BULLET_SOURCES:
        assert sources[rtype][:2] == (rel, id_field), rtype                   # same file, same id
        records = real_kb[rel]
        for p in paths:                                                       # the field exists in the real KB
            assert any(cv_match.dig(r, p) for r in records), (rtype, p)
    assert set(cv_match.KEY_PAIRS) <= ALL_TYPES and set(cv_match.ITEM_QUERY_PREFIX) <= ALL_TYPES
    for rtype, pairs in cv_match.KEY_PAIRS.items():
        rel, _, meta_fn = sources[rtype]
        written = {"type", "source_id"} | {k for r in real_kb[rel] for k in meta_fn(r)}
        for _, theirs in pairs:
            assert theirs == cv_match.DOCUMENT or theirs in written, (rtype, theirs)
    assert set(SECTION_TO_KB_TYPE.values()) - {None} <= ALL_TYPES


# --- the CV-line matcher over a real in-memory index ------------------------------------------
class UnitReranker(Reranker):
    """The real rerank ordering; score() = share of query words found in the document, in [0, 1]."""

    def __init__(self):
        self.scored: list[str] = []

    def score(self, query, documents):
        self.scored.append(query)
        q = set(_tokens(query))
        return [round(len(q & set(_tokens(d))) / len(q), 4) if q else 0.0 for d in documents]


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return super().embed(texts)


_PROFILE_ROWS = [
    ("project:p1", "Project: Aave Risk Monitor. Domain: DeFi. Skills: Python, SQL. Built a DeFi risk monitor.",
     {"type": "project", "source_id": "p1", "title": "Aave Risk Monitor"}),
    ("project:p2", "Project: Churn Model. Domain: Retail. Skills: Python, XGBoost. Predicted churn.",
     {"type": "project", "source_id": "p2", "title": "Churn Model"}),
    ("skill:s1", "Skill: Python (language, advanced). Keywords: pandas, numpy.",
     {"type": "skill", "source_id": "s1", "name": "Python", "category": "language"}),
    ("skill:s2", "Skill: SQL (language, advanced). Keywords: postgres.",
     {"type": "skill", "source_id": "s2", "name": "SQL", "category": "language"}),
    ("coursework:c1", "Course: Databases at TU. Topics: SQL, indexing.",
     {"type": "coursework", "source_id": "c1", "course": "Databases"}),
    ("work_experience:w1", "Data Engineer at Acme. Built pipelines. Technologies: Python, Airflow.",
     {"type": "work_experience", "source_id": "w1", "company": "Acme", "role": "Data Engineer"}),
]
_BULLET_ROWS = [
    ("project:p1#b0", "Monitored Aave positions in Python", {"type": "project", "parent_id": "project:p1", "bullet_index": 0}),
    ("project:p2#b0", "Predicted churn with XGBoost", {"type": "project", "parent_id": "project:p2", "bullet_index": 0}),
]


@pytest.fixture
def matcher(store):
    """A Matcher over one in-memory store holding both collections; nothing is downloaded."""
    def make(rows=_PROFILE_ROWS, bullets=_BULLET_ROWS, embedder=None):
        if embedder is not None:
            store.embedder = embedder
        rr = UnitReranker()
        for col, rs in ((cv_match.PROFILE_COLLECTION, rows), (cv_match.BULLET_COLLECTION, bullets)):
            if rs:
                store.add(col, [r[0] for r in rs], [r[1] for r in rs], [r[2] for r in rs])
        prof = cv_match.VectorTable.load(store._collection(cv_match.PROFILE_COLLECTION))
        bul = cv_match.VectorTable.load(store._collection(cv_match.BULLET_COLLECTION))
        return cv_match.Matcher(store.embedder, rr, prof, bul, cv_match.EmbeddedRetriever(store, rr, prof),
                                cv_match.EmbeddedRetriever(store, rr, bul), k=cv_match.K_CANDIDATES)
    return make


def _type_of(m, rid):
    return m.profile.metas[m.profile.row[rid]].get("type")


def test_the_vector_table_holds_the_collection_by_type_and_scores_its_own_vectors(store):
    """Catches rows mixed across types, or a cosine read from the wrong row."""
    store.add("profile", [r[0] for r in _PROFILE_ROWS], [r[1] for r in _PROFILE_ROWS], [r[2] for r in _PROFILE_ROWS])
    table = cv_match.VectorTable.load(store._collection("profile"))
    assert sorted(table.ids) == sorted(r[0] for r in _PROFILE_ROWS) and table.vecs.shape == (len(_PROFILE_ROWS), DIM)
    assert sorted(table.ids[i] for i in table.rows("skill")) == ["skill:s1", "skill:s2"]
    assert list(table.rows("education")) == []
    own = np.asarray(FakeEmbedder().embed([_PROFILE_ROWS[0][1]])[0], dtype=np.float32)
    assert table.cos_of("project:p1", own) == pytest.approx(1.0, abs=1e-3)
    assert table.cos_of("project:nope", own) is None


def test_the_embedded_retriever_reuses_the_line_vector_and_never_asks_for_more_rows_than_exist(store):
    """Catches a second embedding per search, or Chroma asked for k past a type's row count."""
    emb = CountingEmbedder()
    store.embedder = emb
    store.add("profile", [r[0] for r in _PROFILE_ROWS], [r[1] for r in _PROFILE_ROWS], [r[2] for r in _PROFILE_ROWS])
    table = cv_match.VectorTable.load(store._collection("profile"))
    retr = cv_match.EmbeddedRetriever(store, UnitReranker(), table)
    retr.vectors["Skill: SQL"] = np.asarray(emb.embed(["Skill: SQL"])[0], dtype=np.float32)
    before = emb.calls
    hits = retr.semantic("profile", "Skill: SQL", k=50, where={"type": "skill"})
    assert emb.calls == before
    assert sorted(h.id for h in hits) == ["skill:s1", "skill:s2"] and hits[0].id == "skill:s2"
    retr.vectors["Course: x"] = retr.vectors["Skill: SQL"]
    assert retr.semantic("profile", "Course: x", k=5, where={"type": "education"}) == []
    retr.semantic("profile", "never embedded", k=2, where={"type": "skill"})   # falls back to the store
    assert emb.calls == before + 1


def test_the_matcher_links_every_line_to_the_right_record_of_its_own_section(matcher):
    """Catches a line linked across sections, a matchable line left without a link, or the header linked."""
    m = matcher()
    tree = _matcher_tree()
    m.run(tree)
    jobs, skipped = cv_match.plan_jobs(tree)
    assert set(m.links) == {n.node_id for n, _ in jobs} and "header.0" not in m.links
    for node, kb_type in jobs:
        assert all(_type_of(m, rid) == kb_type for rid in m.links[node.node_id].source_ids), node.node_id
    first = {nid: (link.source_ids or [None])[0] for nid, link in m.links.items()}
    assert first["projects.0"] == "project:p1" and m.details["projects.0"]["reason"].startswith("exact key match")
    assert first["projects.0.b0"] == "project:p1"
    assert first["skills.0.i0"] == "skill:s1" and first["skills.0.i1"] == "skill:s2"
    assert first["coursework.i0"] == "coursework:c1" and first["experience.0"] == "work_experience:w1"
    assert sum(m.out_of_scope.values()) == 0


def test_a_line_with_nothing_to_search_or_nothing_to_meet_is_unmatched_and_cites_nothing(matcher):
    """Catches an empty bullet or a section with no records of its type borrowing some other record."""
    m = matcher()
    m.run(_matcher_tree())
    for nid, why in (("projects.0.b1", "empty query"), ("achievements.i0", "no 'achievement' records")):
        link = m.links[nid]
        assert (link.status, link.source_ids, link.score) == (MatchStatus.UNMATCHED, [], 0.0), nid
        assert m.details[nid]["reason"].startswith(why), nid


def test_every_line_is_embedded_in_one_batch_never_per_search(matcher):
    """Catches a per-line or per-search embedding call (74 lines x 2 channels of model time)."""
    emb = CountingEmbedder()
    m = matcher(embedder=emb)
    emb.calls = 0
    m.run(_matcher_tree())
    assert emb.calls == 1


def test_a_type_filter_that_slips_is_dropped_counted_and_never_linked(matcher):
    """Catches a wrong-type hit reaching a link because the store's filter was trusted."""
    m = matcher()
    real = m.profile_retr.hybrid

    def leaky(collection, query, k=5, fetch=20, where=None):
        stray = Hit(id="skill:s1", document="Skill: Python", metadata={"type": "skill"}, score=1.0,
                    distance=0.0, rerank_score=9.0)
        return real(collection, query, k=k, fetch=fetch, where=where) + [stray]

    m.profile_retr.hybrid = leaky
    m.run(_matcher_tree())
    assert m.out_of_scope["project"] > 0 and m.out_of_scope["coursework"] > 0
    for nid in ("projects.0", "projects.0.b0", "coursework.i0", "experience.0"):
        assert "skill:s1" not in m.links[nid].source_ids, nid
    assert m.links["skills.0.i0"].source_ids[0] == "skill:s1"          # in its own section it is fine


def test_the_same_cv_links_the_same_way_every_run(matcher):
    """Catches order-dependent ties or state carried between Matcher runs."""
    first, second = matcher(), matcher()
    first.run(_matcher_tree())
    second.run(_matcher_tree())
    dump = lambda m: {k: v.model_dump(mode="json") for k, v in m.links.items()}
    assert dump(first) == dump(second)
    assert first.details == second.details


def test_the_matcher_output_is_plain_data_and_written_as_given(matcher, tmp_path):
    """Catches numpy values in the details (the JSON write would crash) or links that differ on disk."""
    m = matcher()
    tree = _matcher_tree()
    m.run(tree)
    json.dumps(m.details)
    tree_file, links_file = cv_match.write_outputs(tree, m, tmp_path)
    payload = json.loads(links_file.read_text(encoding="utf-8"))
    assert payload["links"] == {k: v.model_dump(mode="json") for k, v in m.links.items()}
    assert payload["thresholds"]["provisional"] is True
    assert set(payload["section_scope"]) == {s.value for s in SectionType}
    assert CVTree.model_validate_json(tree_file.read_text(encoding="utf-8")) == tree


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #50 → Data Storage role file §7 S1: the match outputs are not written atomically")
def test_an_interrupted_output_write_never_leaves_a_torn_file(matcher, tmp_path, monkeypatch):
    """Catches a half-written links.json that the next reader silently mis-parses."""
    m = matcher()
    tree = _matcher_tree()
    m.run(tree)
    cv_match.write_outputs(tree, m, tmp_path)
    real = Path.write_text

    def torn(self, data, *args, **kwargs):
        real(self, data[: len(data) // 2], *args, **kwargs)
        raise OSError("No space left on device")

    with monkeypatch.context() as mp:
        mp.setattr(Path, "write_text", torn)
        with pytest.raises(OSError):
            cv_match.write_outputs(tree, m, tmp_path)
    for path in tmp_path.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #50 → Data Storage role file §7 M3: a same-title achievement tie is settled by id order")
def test_an_achievement_tie_goes_to_the_record_with_the_cvs_date(matcher, monkeypatch, tmp_path):
    """Catches "2nd place DeFi Challenge (Nov 2024)" linked to the 2017 record because its id sorts first."""
    monkeypatch.setattr(config, "KB_DIR", _write_kb(tmp_path / "kb", {"profile/achievements.json": [
        {"achievement_id": "ach_033", "title": "2nd place DeFi Challenge", "date": "2017-05"},
        {"achievement_id": "ach_041", "title": "2nd place DeFi Challenge", "date": "2024-11"}]}))
    text = "Achievement: 2nd place DeFi Challenge (hackathon). Won second place."
    rows = [(f"achievement:{i}", text, {"type": "achievement", "source_id": i, "category": "hackathon"})
            for i in ("ach_033", "ach_041")]
    m = matcher(rows=rows, bullets=[])
    A = SectionType.ACHIEVEMENTS
    tree = CVTree(source_file="cv.pdf", root=CVNode(node_id="cv", kind=NodeKind.CV, section_type=SectionType.OTHER,
                  depth=0, children=[_cvn("achievements", NodeKind.SECTION, A, title="Awards", children=[
                      _cvn("achievements.i0", NodeKind.ITEM, A, "2nd place DeFi Challenge (Nov 2024)")])]))
    m.run(tree)
    assert m.links["achievements.i0"].source_ids[0] == "achievement:ach_041"


@pytest.mark.xfail(strict=True, reason="bugs_audit_fixed.md #50 → Data Storage role file §7 S2: the bullet index rebuilds only on a count change")
def test_an_edited_bullet_is_matched_against_its_new_text(store, monkeypatch, tmp_path):
    """Catches a stale sandbox bullet index: same number of bullets, different text, never re-embedded."""
    def kb(one_line):
        return _write_kb(tmp_path / "kb", {"profile/projects.json": [
            {"project_id": "p1", "resume_material": {"one_line": one_line}}]})

    monkeypatch.setattr(config, "KB_DIR", kb("Built a DeFi risk monitor."))
    cv_match.build_bullet_index(store, {"project:p1"}, rebuild=False)
    kb("Built a Uniswap fee dashboard.")
    table = cv_match.build_bullet_index(store, {"project:p1"}, rebuild=False)
    assert table.docs == ["Built a Uniswap fee dashboard."]


def test_the_bullet_index_is_built_once_and_rebuilt_when_its_size_changes(store, monkeypatch, tmp_path):
    """Catches a re-embed on every load, or a grown fixture never reaching the index."""
    emb = CountingEmbedder()
    store.embedder = emb

    def kb(*bullets):
        return _write_kb(tmp_path / "kb", {"profile/projects.json": [
            {"project_id": "p1", "resume_material": {"full_bullet_points": list(bullets)}}]})

    monkeypatch.setattr(config, "KB_DIR", kb("one", "two"))
    assert sorted(cv_match.build_bullet_index(store, {"project:p1"}, rebuild=False).docs) == ["one", "two"]
    calls = emb.calls
    cv_match.build_bullet_index(store, {"project:p1"}, rebuild=False)
    assert emb.calls == calls                                           # nothing changed, nothing embedded
    kb("one", "two", "three")
    assert sorted(cv_match.build_bullet_index(store, {"project:p1"}, rebuild=False).docs) == ["one", "three", "two"]


# --- the matcher's loader: refuses an unusable index before loading the reranker --------------
@pytest.fixture
def loader_env(monkeypatch, tmp_path):
    """load_matcher_parts with the models faked and every index in tmp_path."""
    env = SimpleNamespace(dim=DIM, rerankers=0)

    class Emb(FakeEmbedder):
        @property
        def dim(self):
            return env.dim

    class RR(UnitReranker):
        def __init__(self):
            super().__init__()
            env.rerankers += 1

    monkeypatch.setattr(cv_match, "Embedder", Emb)
    monkeypatch.setattr(cv_match, "Reranker", RR)
    monkeypatch.setattr(cv_match, "get_embedder", lambda: Emb())      # the loader uses the shared singletons (#43);
    monkeypatch.setattr(cv_match, "get_reranker", lambda: RR())       # without these it loaded the REAL BGE models (7 s)
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "KB_DIR", _write_kb(tmp_path / "kb", {"profile/projects.json": [
        {"project_id": "p1", "resume_material": {"one_line": "Built a DeFi risk monitor."}}]}))
    env.sandbox = tmp_path / "sandbox"
    env.index = lambda: VectorStore(embedder=FakeEmbedder(), persist_dir=tmp_path / "chroma").add(
        "profile", [r[0] for r in _PROFILE_ROWS], [r[1] for r in _PROFILE_ROWS], [r[2] for r in _PROFILE_ROWS])
    return env


def test_the_loader_refuses_a_missing_profile_index_before_any_reranker_loads(loader_env):
    """Catches a run that loads every model and then links nothing because the index was never built."""
    assert cv_match.load_matcher_parts(index_dir=loader_env.sandbox) is None
    assert loader_env.rerankers == 0


def test_the_loader_refuses_an_index_built_with_another_model(loader_env):
    """Catches vectors of one model searched with another's (a different dimension, at least)."""
    loader_env.index()
    loader_env.dim = DIM * 6
    assert cv_match.load_matcher_parts(index_dir=loader_env.sandbox) is None
    assert loader_env.rerankers == 0


def test_the_loader_returns_the_matchers_parts_over_the_built_index(loader_env):
    """Catches parts in the wrong order for Matcher(*parts), or a bullet index left empty."""
    loader_env.index()
    parts = cv_match.load_matcher_parts(index_dir=loader_env.sandbox)
    embedder, reranker, profile, bullets, profile_retr, bullet_retr = parts
    assert loader_env.rerankers == 1
    assert sorted(profile.ids) == sorted(r[0] for r in _PROFILE_ROWS)
    assert bullets.ids == ["project:p1#b0"]
    assert profile_retr.table is profile and bullet_retr.table is bullets
    cv_match.Matcher(*parts, k=cv_match.K_CANDIDATES)                  # the order cv_link relies on


# --- opt-in: real models, retrieval quality on the real KB -------------------------------------
_REAL_NAMES = {   # record type -> the name a person would search it by
    "project": lambda r: r["basic_info"]["title"],
    "skill": lambda r: r["name"],
    "coursework": lambda r: r["course_name"],
    "work_experience": lambda r: f"{r['role']} at {r['company']}",
}


@pytest.fixture(scope="module")
def real_vectors(tmp_path_factory):
    if os.getenv("RUN_REAL_EMBED") != "1":
        pytest.skip("set RUN_REAL_EMBED=1 to run the real embedding model")
    from vectordb.embeddings import Embedder

    s = VectorStore(embedder=Embedder(), persist_dir=tmp_path_factory.mktemp("real_chroma"))
    ingest.build(s)                                                   # the real KB, read only
    return s


@pytest.mark.parametrize("rtype", sorted(_REAL_NAMES))
def test_real_a_records_own_name_retrieves_it_first(real_vectors, real_kb, rtype):
    """Catches an embedding or text-builder change that stops exact names finding their record (precision@1)."""
    rel, id_field = next((rel, idf) for rel, idf, t, *_ in ingest.SOURCES if t == rtype)
    records = real_kb[rel]
    same_name: dict[str, set[str]] = {}
    for r in records:
        same_name.setdefault(_REAL_NAMES[rtype](r).lower(), set()).add(f"{rtype}:{r[id_field]}")
    retr = Retriever(store=real_vectors)
    misses = []
    for r in records:
        name = _REAL_NAMES[rtype](r)
        (top,) = retr.semantic("profile", name, k=1, where={"type": rtype})
        if top.id not in same_name[name.lower()]:
            misses.append((name, top.id))
    assert len(misses) <= 0.1 * len(records), misses


@pytest.mark.skipif(os.getenv("RUN_REAL_EMBED") != "1" or os.getenv("RUN_REAL_RERANK") != "1"
                    or not config.CV_DEFAULT_PATH.is_file() or not config.VECTORDB_DIR.is_dir(),
                    reason="needs RUN_REAL_EMBED=1, RUN_REAL_RERANK=1, the sample CV and a built index")
def test_real_the_sample_cv_links_every_line_to_the_right_record(tmp_path, monkeypatch):
    """Catches a matching regression on the CV generated from the KB (run 3: 9/9 entries, 27/27 bullets)."""
    import shutil

    index = tmp_path / "chroma"
    shutil.copytree(config.VECTORDB_DIR, index)                         # never open the real index
    monkeypatch.setattr(config, "VECTORDB_DIR", index)
    results = cv_match.match_cvs([config.CV_DEFAULT_PATH], out_dir=None, index_dir=tmp_path / "sandbox", report=False)
    (m,) = results.values()
    tree = cv_extract.parse_cv(config.CV_DEFAULT_PATH)[0]
    jobs, _ = cv_match.plan_jobs(tree)
    assert {n.node_id for n, _ in jobs} == set(m.links) and sum(m.out_of_scope.values()) == 0
    entry_pick = None
    for node, kb_type in jobs:
        link = m.links[node.node_id]
        assert all(_type_of(m, rid) == kb_type for rid in link.source_ids), node.node_id
        if node.kind == NodeKind.ENTRY:
            assert link.status is MatchStatus.MATCHED, node.node_id
            assert m.details[node.node_id]["reason"].startswith("exact key match"), node.node_id
            entry_pick = link.source_ids[0]
        elif node.kind == NodeKind.BULLET:
            assert link.source_ids and link.source_ids[0] == entry_pick, node.node_id
        else:
            assert link.status is not MatchStatus.UNMATCHED, node.node_id
