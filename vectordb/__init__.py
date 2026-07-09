"""
Vector DB for the knowledge base.

  Embedder     - local sentence-transformers embeddings (bge-base-en-v1.5)
  VectorStore  - small Chroma wrapper (cosine; add / query / count)
  build        - embed the knowledge_base/*.json fixtures into collections

Quick start:
    from vectordb import VectorStore, build
    store = VectorStore()          # persistent (config.VECTORDB_DIR)
    build(store)                   # index the knowledge base
    store.query("profile", "machine learning on blockchain data", k=3)
"""

from vectordb.embeddings import Embedder
from vectordb.ingest import build
from vectordb.reranker import Reranker
from vectordb.store import Hit, VectorStore

__all__ = ["Embedder", "VectorStore", "Hit", "build", "Reranker"]
