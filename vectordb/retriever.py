"""
Retriever (Instructions.md #12/14) — the single entry point agents use to pull
evidence from the vector DB.

Layers, cheapest first:
  - semantic(...)   : embedding similarity (wraps VectorStore.query) — DONE
  - reranked(...)   : semantic recall, then cross-encoder precision  — DONE
  - keyword(...)    : exact/fuzzy term overlap                       — YOUR CODE
  - hybrid(...)     : merge semantic + keyword, dedupe, rerank       — YOUR CODE

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

    # --- YOUR CODE: keyword + hybrid -----------------------------------------
    def keyword(self, collection: str, query: str, k: int = 5, where: Optional[dict] = None) -> list[Hit]:
        """Top-k by keyword/term overlap (no embeddings)."""
        hits = self._all_documents(collection, where)

        from rapidfuzz import fuzz
        for h in hits:
            h.score = fuzz.token_set_ratio(query, h.document) / 100.0
        
        hits.sort(key = lambda h: h.score, reverse = True)

        return hits[:k]
        
        
        

    def hybrid(self, collection: str, query: str, k: int = 5, fetch: int = 20, where: Optional[dict] = None) -> list[Hit]:
        """Semantic + keyword combined, deduped by id, then reranked to top-k."""
        sem_antic = self.semantic(collection, query, k = fetch, where = where)
        kw_search = self.keyword(collection, query, k = fetch, where = where)

        best = {}
        for h in sem_antic + kw_search:
            if h.id not in best or h.score > best[h.id].score:
                best[h.id] = h

        merged = list(best.values())

        if self.reranker:
            return self.reranker.rerank(query, merged, top_k =k)
        
        merged.sort(key = lambda h: h.score, reverse = True)

        return merged[:k]
