"""
One embedder and one reranker per process (bugs_audit_fixed.md #43).

The models are the expensive thing in this project, not the code around them:
bge-base is ~440MB resident, bge-reranker-base ~1.1GB. Every module that built
its own paid for another copy — the API process held three embedders and two
rerankers, plus a fourth embedder built and dropped on every gap-answer save.

So: build at most one of each, on first use, and hand the same object out.

  - Lazy. Importing this module loads nothing; `import vectordb` stays cheap.
  - Keyed by model name, so changing config.EMBEDDING_MODEL in a test (or an
    explicit `get_embedder("other/model")`) gets its own instance rather than
    the cached one for a different model.
  - Thread-safe. Two LangGraph nodes entering together build one model, not two
    (double-checked locking, the same pattern as backend/vectorstore.py).

Tests that want a fake model still inject it (`VectorStore(embedder=Fake())`);
nothing here is reached when an embedder is passed in.

    from vectordb.models import get_embedder, get_reranker
    store = VectorStore(embedder=get_embedder())
"""

from __future__ import annotations

import threading

import config

_embedders: dict[str, object] = {}
_rerankers: dict[str, object] = {}
_lock = threading.Lock()


def get_embedder(model_name: str | None = None):
    """The process's Embedder for `model_name` (default config.EMBEDDING_MODEL)."""
    name = model_name or config.EMBEDDING_MODEL
    cached = _embedders.get(name)
    if cached is not None:                       # fast path: no lock once built
        return cached
    with _lock:
        if name not in _embedders:
            from vectordb.embeddings import Embedder   # lazy: pulls in torch

            _embedders[name] = Embedder(name)
        return _embedders[name]


def get_reranker(model_name: str | None = None):
    """The process's Reranker for `model_name` (default config.RERANKER_MODEL)."""
    name = model_name or config.RERANKER_MODEL
    cached = _rerankers.get(name)
    if cached is not None:
        return cached
    with _lock:
        if name not in _rerankers:
            from vectordb.reranker import Reranker     # lazy: pulls in torch

            _rerankers[name] = Reranker(name)
        return _rerankers[name]


def loaded() -> dict[str, list[str]]:
    """Which models this process has actually built. For diagnostics only."""
    return {"embedders": sorted(_embedders), "rerankers": sorted(_rerankers)}


def clear() -> None:
    """Drop the cached models (tests, and a deliberate reload). Not thread-safe."""
    _embedders.clear()
    _rerankers.clear()
