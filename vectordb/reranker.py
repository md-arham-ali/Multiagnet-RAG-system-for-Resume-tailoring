"""
Cross-encoder reranker BAAI/bge-reranker-base.

The Embedder (a bi-encoder) is fast but approximate: it embeds the query and each
document *separately*. A cross-encoder reads the (query, document) pair *together*
and scores their relevance directly more accurate, but too slow to run over a
whole collection. So retrieval is two stages:

    1. retrieve a wider candidate set with the vector store   (recall, cheap)
    2. rerank those candidates with the cross-encoder         (precision)

    >>> from vectordb import VectorStore, Reranker             # doctest: +SKIP
    >>> store, rr = VectorStore(), Reranker()
    >>> store.search("profile", "fraud in crypto wallets", k=3, fetch=20, reranker=rr)
"""

from __future__ import annotations

import config


class Reranker:
    """Scores (query, document) pairs and reorders hits by relevance."""

    def __init__(self, model_name: str = config.RERANKER_MODEL) -> None:
        self.model_name = model_name
        # Lazy import so `import vectordb` stays cheap; the model only loads
        # when a Reranker is actually constructed.
        from utils.trace import step  # TEMP tracing

        with step("importing sentence-transformers (loads PyTorch; slow first time)"):
            from sentence_transformers import CrossEncoder
        with step(f"loading reranker model {model_name} (slow on first load)"):
            self.model = CrossEncoder(model_name)

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Relevance score for each (query, document) pair (higher = better)."""
        pairs = [[query, doc] for doc in documents]
        return [float(s) for s in self.model.predict(pairs)]

    def rerank(self, query, hits, top_k=None):
        """Reorder `hits` by cross-encoder score (sets `hit.rerank_score`)."""
        if not hits:
            return []
        for hit, s in zip(hits, self.score(query, [h.document for h in hits])):
            hit.rerank_score = round(s, 4)
        ranked = sorted(hits, key=lambda h: h.rerank_score, reverse=True)
        return ranked[:top_k] if top_k else ranked
