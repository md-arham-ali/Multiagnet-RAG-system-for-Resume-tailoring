"""
Retriever (Instructions.md #12/14) — the single entry point agents use to pull
evidence from the vector DB.

Layers, cheapest first:
  - semantic(...)   : embedding similarity (wraps VectorStore.query)
  - reranked(...)   : semantic recall, then cross-encoder precision
  - keyword(...)    : query-term coverage + fuzzy term overlap
  - hybrid(...)     : merge semantic + keyword by rank (RRF), dedupe, rerank

Every channel takes a k, and k <= 0 means "no hits" at all of them (#80.1).

Test each independently with sample queries before any agent calls it.
"""

from __future__ import annotations

from typing import Optional

from vectordb.store import Hit, VectorStore


class Retriever:
    def __init__(self, store: VectorStore | None = None, reranker=None) -> None:
        self.store = store or VectorStore()
        self.reranker = reranker  # a vectordb.Reranker, or None

    # --- DONE: semantic + reranked -------------------------------------------
    def semantic(self, collection: str, query: str, k: int = 5, where: Optional[dict] = None) -> list[Hit]:
        """Top-k by embedding similarity."""

        return self.store.query(collection, query, k=k, where=where)

    def reranked(self, collection: str, query: str, k: int = 5, fetch: int = 20, where: Optional[dict] = None) -> list[Hit]:
        """Fetch a wide candidate set, then sharpen with the cross-encoder."""

        return self.store.search(collection, query, k=k, fetch=fetch, reranker=self.reranker, where=where)

    # --- helper: pull raw docs for keyword scanning (boilerplate) ------------
    def _all_documents(self, collection: str, where: Optional[dict] = None) -> list[Hit]:
        """Every (id, document, metadata) in a collection, no embedding involved."""
        res = self.store._collection(collection).get(where=where or None)

        return [
            Hit(id=i, document=d, metadata=m or {}, score=0.0, distance=1.0)
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        ]

    # --- keyword + hybrid ----------------------------------------------------
    # How a keyword hit is scored (#64.1, #64.2):
    #   coverage  = share of the query's terms the document actually contains,
    #               a term counting as present on an exact token match or a
    #               close fuzzy one (typos still match: "pyhton" -> "python")
    #   overlap   = rapidfuzz token_set_ratio, the old whole-string score
    # score = COVERAGE_WEIGHT * coverage + (1 - COVERAGE_WEIGHT) * overlap.
    #
    # Why not token_set_ratio alone: it returns 100 whenever one token set
    # contains the other, so a record that is just "sql" tied a record holding
    # every query term, and ties then fell back to insertion order. Coverage is
    # what separates them; the ratio is kept as the tie-breaker because it still
    # rewards a document that is mostly about the query.
    #
    # Both sides go through rapidfuzz's default processor, which lowercases and
    # drops punctuation. Without it "Skills: Python, SQL." tokenizes to
    # "Skills:"/"Python,"/"SQL." and never matches "python"/"sql" at all.
    COVERAGE_WEIGHT = 0.7
    TERM_MATCH = 85.0           # fuzz.ratio needed to call one term the other

    @staticmethod
    def _wants_nothing(k: int) -> bool:
        return k is None or k < 1

    @classmethod
    def _keyword_score(cls, query_terms: list[str], document: str) -> float:
        """Score one document against already-processed query terms, in [0, 1]."""
        from rapidfuzz import fuzz, utils

        doc = utils.default_process(document or "")
        overlap = fuzz.token_set_ratio(" ".join(query_terms), doc) / 100.0
        if not query_terms:
            return round(overlap, 4)

        doc_terms = doc.split()
        covered = 0
        for term in query_terms:
            if term in doc_terms or any(
                fuzz.ratio(term, d) >= cls.TERM_MATCH for d in doc_terms
            ):
                covered += 1
        coverage = covered / len(query_terms)
        return round(cls.COVERAGE_WEIGHT * coverage
                     + (1.0 - cls.COVERAGE_WEIGHT) * overlap, 4)

    def keyword(self, collection: str, query: str, k: int = 5, where: Optional[dict] = None) -> list[Hit]:
        """Top-k by keyword/term overlap (no embeddings)."""
        if self._wants_nothing(k):
            return []

        from rapidfuzz import utils

        hits = self._all_documents(collection, where)
        terms = utils.default_process(query or "").split()
        for h in hits:
            h.score = self._keyword_score(terms, h.document)
            h.distance = round(1.0 - h.score, 4)    # Hit.distance is documented 1 - score

        hits.sort(key=lambda h: h.score, reverse=True)

        return hits[:k]


    # How the two channels are merged (audit #4):
    # cosine similarity (~0.4-0.8 on real text) and the keyword score (0.9-1.0
    # whenever a few query words appear) are not on one scale, so a raw `max`
    # per id handed the merge to whichever channel scores higher in general,
    # which is the keyword one. Ranks are comparable across channels, scores are
    # not, so each hit gets reciprocal rank fusion: the sum over channels of
    # 1 / (RRF_K + rank), rank counted from 1. A record both channels place
    # high beats one only a single channel likes, and neither scale can win.
    RRF_K = 60       # the constant from the RRF paper; it flattens the gap between ranks

    def hybrid(self, collection: str, query: str, k: int = 5, fetch: int = 20, where: Optional[dict] = None) -> list[Hit]:
        """Semantic + keyword fused by rank, deduped by id, then reranked to top-k.

        Without a reranker the fused order is the answer. `Hit.score` is then the
        fused score as a share of the best possible one (first in both channels
        = 1.0, first in just one = about 0.5), in [0, 1] like every other score.
        `distance` stays whatever the first channel to return the hit reported.
        """
        if self._wants_nothing(k):
            return []
        channels = (
            self.semantic(collection, query, k=fetch, where=where),
            self.keyword(collection, query, k=fetch, where=where),
        )

        fused: dict[str, float] = {}
        first: dict[str, Hit] = {}                  # insertion order: semantic hits, then keyword-only ones
        for hits in channels:
            for rank, h in enumerate(hits, start=1):
                fused[h.id] = fused.get(h.id, 0.0) + 1.0 / (self.RRF_K + rank)
                first.setdefault(h.id, h)

        ceiling = len(channels) / (self.RRF_K + 1)  # first place in every channel
        for id_, h in first.items():
            h.score = round(fused[id_] / ceiling, 4)

        merged = sorted(first.values(), key=lambda h: h.score, reverse=True)   # stable: ties keep semantic order

        if self.reranker:
            return self.reranker.rerank(query, merged, top_k=k)

        return merged[:k]
