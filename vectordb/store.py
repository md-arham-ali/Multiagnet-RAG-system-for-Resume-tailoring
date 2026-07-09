"""
A small Chroma-backed vector store.

Deliberately simple and explicit:
  - embed text ourselves (Embedder) and hand Chroma the vectors. So the
    embedding step is visible and the collection needs no embedding-function setup.
  - Cosine space (vectors are normalized) -> a hit's `score = 1 - distance` is
    just cosine similarity in [0, 1] (1.0 = identical).
  - The Embedder is injectable, so tests pass a fast fake one (no model download).

    >>> store = VectorStore(in_memory=True)                       # doctest: +SKIP
    >>> store.add("profile", ["p1"], ["python and sql"], [{"type": "skill"}])
    >>> store.query("profile", "sql developer", k=1)[0].id
    'p1'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chromadb

import config
from vectordb.embeddings import Embedder


@dataclass
class Hit:
    """One search result."""

    id: str
    document: str
    metadata: dict
    score: float       # cosine similarity in [0, 1] (higher = more similar)
    distance: float    # cosine distance = 1 - score
    rerank_score: float | None = None   # set when a cross-encoder reranks the hit


class VectorStore:
    """Thin wrapper over a Chroma client + named collections."""

    def __init__(self, embedder=None, persist_dir=None, in_memory: bool = False) -> None:
        from utils.trace import log  # TEMP tracing
        self.embedder = embedder or Embedder()
        if in_memory:
            self.client = chromadb.EphemeralClient()      # nothing written to disk
        else:
            path = str(persist_dir or config.VECTORDB_DIR)
            log(f"opening Chroma store at {path}")
            self.client = chromadb.PersistentClient(path=path)

    def _collection(self, name: str):
        # Cosine space; no Chroma embedding function (we always pass vectors).
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def add(self, collection: str, ids, texts, metadatas) -> None:
        """Embed `texts` and upsert them. Idempotent: re-adding an id overwrites."""
        self._collection(collection).upsert(
            ids=list(ids),
            embeddings=self.embedder.embed(list(texts)),
            documents=list(texts),
            metadatas=list(metadatas),
        )

    def query(
        self,
        collection: str,
        text: str,
        k: int = 5,
        where: Optional[dict] = None,
    ) -> list[Hit]:
        """Return the top-k most similar items, optionally filtered by metadata."""
        from utils.trace import log  # TEMP tracing
        log(f"semantic search in '{collection}' (k={k}{', filtered' if where else ''}): {text[:50]!r}")
        res = self._collection(collection).query(
            query_embeddings=self.embedder.embed([text]),
            n_results=k,
            where=where or None,
        )
        hits: list[Hit] = []
        for id_, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append(
                Hit(
                    id=id_,
                    document=doc,
                    metadata=meta or {},
                    score=round(1.0 - dist, 4),
                    distance=round(dist, 4),
                )
            )
        return hits

    def search(self, collection, query, k=5, fetch=20, reranker=None, where=None):
        """Vector search, optionally refined by a cross-encoder reranker.

        Without a reranker: top-k by embedding similarity (same as ``query``).
        With a reranker: fetch ``fetch`` candidates, then rerank down to top-k.
        """
        n = fetch if reranker is not None else k
        hits = self.query(collection, query, k=n, where=where)
        if reranker is not None:
            hits = reranker.rerank(query, hits, top_k=k)
        return hits

    def count(self, collection: str) -> int:
        return self._collection(collection).count()

    def reset(self, collection: str) -> None:
        """Drop a collection if it exists (used before a fresh re-ingest)."""
        try:
            self.client.delete_collection(collection)
        except Exception:
            pass
