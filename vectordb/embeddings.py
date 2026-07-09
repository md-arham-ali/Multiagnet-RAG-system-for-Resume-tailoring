"""
Local text embeddings, sentence-transformers, BAAI/bge-base-en-v1.5.

Free, local, Vectors are L2-normalized so the vector store can use
cosine similarity (cosine === dot product for unit vectors).

Kept short on purpose, so the embedding step is easy to see and analyze:

    >>> from vectordb.embeddings import Embedder
    >>> e = Embedder()
    >>> v = e.embed(["machine learning on blockchain data"])[0]
    >>> len(v)          # 768 for bge-base
    768
"""

from __future__ import annotations

import config


class Embedder:
    """Turns text into normalized embedding vectors."""

    def __init__(self, model_name: str = config.EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        # only loads when an Embedder is actually constructed.
        from utils.trace import step, log  # TEMP tracing

        with step("importing sentence-transformers (loads PyTorch; slow first time)"):
            from sentence_transformers import SentenceTransformer
        with step(f"loading embedding model {model_name} (is ~440MB; so slow on first load)"):
            self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings -> a list of normalized float vectors."""
        vectors = self.model.encode(
            list(texts),
            normalize_embeddings=True,   # unit vectors -> cosine similarity
            convert_to_numpy=True,
        )
        return vectors.tolist()

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()
