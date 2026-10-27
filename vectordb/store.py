"""
A small Chroma-backed vector store.

Deliberately simple and explicit:
  - embed text ourselves (Embedder) and hand Chroma the vectors. So the
    embedding step is visible and the collection needs no embedding-function setup.
  - Cosine space (vectors are normalized) -> a hit's `score = 1 - distance` is
    just cosine similarity, clamped to [0, 1] (1.0 = identical). Chroma's cosine
    distance runs [0, 2], so a genuinely dissimilar hit would score negative and
    break the range `Hit.score` documents and `Retriever.hybrid` compares
    against keyword scores (#38).
  - The Embedder is injectable, so tests pass a fast fake one (no model download).

    >>> store = VectorStore(in_memory=True)                       # doctest: +SKIP
    >>> store.add("profile", ["p1"], ["python and sql"], [{"type": "skill"}])
    >>> store.query("profile", "sql developer", k=1)[0].id
    'p1'
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import chromadb

import config
from vectordb.models import get_embedder


log = logging.getLogger("vectordb")

BACKUP_SUFFIX = "__old"     # a live collection's name while a swap is in flight


class CollectionNotFound(LookupError):
    """A read named a collection that has never been built."""


class IndexModelMismatch(RuntimeError):
    """A collection was built with a different embedding model than this store embeds with."""


@dataclass
class Hit:
    """One search result."""

    id: str
    document: str
    metadata: dict
    score: float       # similarity in [0, 1] (higher = more similar), clamped
    distance: float    # cosine distance as Chroma reported it, unclamped
    rerank_score: float | None = None   # set when a cross-encoder reranks the hit


class VectorStore:
    """Thin wrapper over a Chroma client + named collections."""

    def __init__(self, embedder=None, persist_dir=None, in_memory: bool = False) -> None:
        from utils.trace import log  # TEMP tracing
        # No embedder passed -> the process's shared one (#43), never a new model.
        self.embedder = embedder or get_embedder()
        if in_memory:
            self.client = chromadb.EphemeralClient()      # nothing written to disk
        else:
            path = str(persist_dir or config.VECTORDB_DIR)
            log(f"opening Chroma store at {path}")
            self.client = chromadb.PersistentClient(path=path)

    def _collection(self, name: str):
        """Read door: open an existing collection, never create one.

        A missing collection raises instead of returning an empty one, so an
        unbuilt or misnamed index fails loudly rather than yielding no evidence.
        """
        if not self.exists(name):
            raise CollectionNotFound(
                f"collection {name!r} has not been built; build it with scripts/build_vectordb.py"
            )
        return self.client.get_collection(name=name, embedding_function=None)

    def _model(self):
        # An injected embedder with no model_name (a bare fake) is simply unchecked.
        return getattr(self.embedder, "model_name", None)

    def _writable(self, name: str):
        # Write door. Cosine space; no Chroma embedding function (we always pass vectors).
        # The model name is stamped at creation only: Chroma ignores metadata on an
        # existing collection, so an older, unstamped index stays unstamped.
        meta = {"hnsw:space": "cosine"}
        if self._model():
            meta["embedding_model"] = self._model()
        return self.client.get_or_create_collection(
            name=name,
            metadata=meta,
            embedding_function=None,
        )

    def _check_model(self, col, name: str) -> None:
        # Vectors of one model searched or mixed with another's still "work" (same
        # dimension), they just return near-random evidence. So refuse (#80.2).
        # An unstamped (pre-fix) index can't be judged here, it passes.
        want, have = self._model(), (col.metadata or {}).get("embedding_model")
        if want and have and want != have:
            raise IndexModelMismatch(
                f"collection {name!r} was built with embedding model {have!r} but this store "
                f"embeds with {want!r}; rebuild it with scripts/build_vectordb.py"
            )

    def check_model(self, collection: str) -> None:
        """Raise IndexModelMismatch if `collection` was built with another embedding model."""
        self._check_model(self._collection(collection), collection)

    @staticmethod
    def _wants_nothing(k: int) -> bool:
        # k <= 0 means "no hits". Python turns 0 and -1 into "all" and "all but
        # one" through slicing and truthiness, so every door that takes a k says
        # so explicitly instead (#80.1).
        return k is None or k < 1

    def exists(self, collection: str) -> bool:
        return collection in [getattr(c, "name", c) for c in self.client.list_collections()]

    def add(self, collection: str, ids, texts, metadatas) -> None:
        """Embed `texts` and upsert them. Idempotent: re-adding an id overwrites."""
        col = self._writable(collection)
        self._check_model(col, collection)      # before the (slow) embed, and before any write
        col.upsert(
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
        """Return the top-k most similar items, optionally filtered by metadata.

        k <= 0 returns [] without touching Chroma (which would raise on it).
        """
        if self._wants_nothing(k):
            return []
        from utils.trace import log  # TEMP tracing
        log(f"semantic search in '{collection}' (k={k}{', filtered' if where else ''}): {text[:50]!r}")
        col = self._collection(collection)
        self._check_model(col, collection)
        res = col.query(
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
                    score=round(max(0.0, 1.0 - dist), 4),   # clamped, see Hit (#38)
                    distance=round(dist, 4),
                )
            )
        return hits

    def search(self, collection, query, k=5, fetch=20, reranker=None, where=None):
        """Vector search, optionally refined by a cross-encoder reranker.

        Without a reranker: top-k by embedding similarity (same as ``query``).
        With a reranker: fetch ``fetch`` candidates, then rerank down to top-k.
        """
        if self._wants_nothing(k):
            return []                       # not "fetch everything and rerank" (#80.1)
        n = fetch if reranker is not None else k
        hits = self.query(collection, query, k=n, where=where)
        if reranker is not None:
            hits = reranker.rerank(query, hits, top_k=k)
        return hits

    def count(self, collection: str) -> int:
        """Records in `collection`; 0 for one never built (and it stays unbuilt)."""
        return self._collection(collection).count() if self.exists(collection) else 0

    def delete(self, collection: str, ids) -> int:
        """Remove `ids` from `collection`. Returns how many ids were asked for.

        An edit or a removal upstream has to be able to take the old vector out,
        or it stays retrievable beside the new one (bug#27, bug#30) and an
        account deletion leaves that account's evidence searchable. Unknown ids
        are a no-op in Chroma, and a missing collection raises CollectionNotFound.
        """
        ids = list(ids)
        if not ids:
            return 0
        self._collection(collection).delete(ids=ids)
        return len(ids)

    def drop_collection(self, collection: str) -> bool:
        """Delete a whole collection. True if one was there, False if not.

        `reset` is the same operation named for re-ingest; this is the name the
        per-profile layer (§13.3) and account deletion ask for.
        """
        if not self.exists(collection):
            return False
        self.client.delete_collection(collection)
        return True

    def swap(self, pairs: dict) -> None:
        """Promote staged collections to their live names, undoing it all on a failure.

        `pairs` maps a live name to the staged collection that replaces it, or to
        None to remove the live one. Each live collection is renamed to
        `<name>__old` first and dropped only once every promotion has worked, so
        a failure puts the old collections back instead of leaving a half-built
        index (#65.2). Renames touch no vectors, so nothing is embedded here.
        """
        # (live name, whether the old live collection was renamed to its backup).
        # Only a collection that got that far has anything to undo: a rename that
        # failed leaves the live one untouched, and it must not be dropped.
        done: list[tuple[str, bool]] = []
        try:
            for live, staged in pairs.items():
                backup = live + BACKUP_SUFFIX
                self.drop_collection(backup)            # left over from an interrupted swap
                backed_up = self.exists(live)
                if backed_up:
                    self._open(live).modify(name=backup)
                done.append((live, backed_up))          # after the rename, not before it
                if staged is not None:
                    self._open(staged).modify(name=live)
        except Exception:
            for live, backed_up in reversed(done):      # best effort, one step must not stop the rest
                backup = live + BACKUP_SUFFIX
                try:
                    self.drop_collection(live)          # the promoted one, or nothing if the promotion failed
                    if backed_up:
                        self._open(backup).modify(name=live)
                except Exception:
                    log.exception("swap rollback failed for %r; the old index is under %r", live, backup)
            raise
        for live, backed_up in done:
            try:
                self.drop_collection(live + BACKUP_SUFFIX)
            except Exception:
                log.exception("could not drop the old %r after a swap; the next swap removes it", live)

    def _open(self, name: str):
        return self.client.get_collection(name=name, embedding_function=None)

    def reset(self, collection: str) -> None:
        """Drop a collection if it exists (used before a fresh re-ingest)."""
        # Check existence explicitly instead of `except Exception: pass`, which
        # also silenced real failures (permissions, corrupt index, wrong path).
        if self.exists(collection):
            self.client.delete_collection(collection)
