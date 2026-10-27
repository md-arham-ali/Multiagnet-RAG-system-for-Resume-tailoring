"""
One VectorStore for the whole API process.

Lazy and shared on purpose. Constructing it loads a ~440MB embedding model, so
it must not happen at import (that is the boot cost moved off the request path
on 2026-08-19), and it must not happen twice — two modules each holding their
own instance means two copies of the model in memory.
"""

from __future__ import annotations

import threading

import config

_store = None
_lock = threading.Lock()


def get_vector_store():
    """The process's VectorStore. First call loads the embedder (~20s)."""
    global _store
    with _lock:
        if _store is None:
            from vectordb.store import VectorStore  # lazy: pulls in torch

            _store = VectorStore(persist_dir=config.VECTORDB_DIR)
        return _store


def profile_index_problem() -> str | None:
    """Why a run would fail when it reaches retrieval / `cv_link`, or None.

    Chroma only — deliberately does NOT go through `get_vector_store()`, so a
    readiness check costs no model load (that is the whole reason this is not
    `store.count("profile")`). Read-only: `get_collection`, never
    `get_or_create`, so asking never builds the thing it is asking about.

    The model stamp is compared against `config.EMBEDDING_MODEL` rather than a
    live `Embedder().model_name` for the same reason; they are the same string,
    and `vectordb/store.py` writes the stamp from the embedder's own name.

    Returns a sentence fit for a log line or a 503 body, naming the fix.
    """
    from utils.cv_handling.cv_match import PROFILE_COLLECTION

    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(config.VECTORDB_DIR))
        names = [getattr(c, "name", c) for c in client.list_collections()]
        if PROFILE_COLLECTION not in names:
            return (f"the {PROFILE_COLLECTION!r} collection has not been built; "
                    f"build it with scripts/build_vectordb.py")
        col = client.get_collection(name=PROFILE_COLLECTION, embedding_function=None)
        if col.count() == 0:
            return (f"the {PROFILE_COLLECTION!r} collection is empty; "
                    f"build it with scripts/build_vectordb.py")
        stamp = (col.metadata or {}).get("embedding_model")
        if stamp and stamp != config.EMBEDDING_MODEL:
            return (f"the {PROFILE_COLLECTION!r} collection was built with embedding model "
                    f"{stamp!r} but this process embeds with {config.EMBEDDING_MODEL!r}; "
                    f"rebuild it with scripts/build_vectordb.py")
        return None
    except Exception as exc:
        # Fail open, and say so: an unreadable index is a real problem, but a
        # readiness probe that cannot read it must not be mistaken for proof
        # that the index is broken.
        return f"the index could not be read ({type(exc).__name__}: {exc})"
