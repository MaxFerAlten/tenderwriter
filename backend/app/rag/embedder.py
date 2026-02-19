"""
TenderWriter — Embedding Model Wrapper

Wraps sentence-transformers for generating text embeddings with batch
processing and optional caching.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import structlog

from app.config import settings

logger = structlog.get_logger()


class Embedder:
    """
    Generates dense vector embeddings for text using sentence-transformers.

    Supports batch processing and device selection (CPU/GPU).
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        batch_size: int | None = None,
    ):
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model = None

    @property
    def model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading embedding model",
                model=self.model_name,
                device=self.device,
            )
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
            logger.info(
                "Embedding model loaded",
                dimension=self._model.get_sentence_embedding_dimension(),
            )
        return self._model

    @property
    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        return self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns a 1D numpy array."""
        return self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """
        Embed a batch of texts. Returns a 2D numpy array (N x dimension).

        Processes in batches of `self.batch_size` to manage memory.
        """
        if not texts:
            return np.array([])

        logger.debug("Embedding batch", count=len(texts), batch_size=self.batch_size)

        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        logger.debug("Embedding complete", shape=embeddings.shape)
        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a query string.

        For asymmetric models (like BGE), prepend the query instruction.
        """
        # BGE models require a query prefix for retrieval
        if "bge" in self.model_name.lower():
            query = f"Represent this sentence for searching relevant passages: {query}"

        return self.embed(query)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Singleton factory for the embedder instance."""
    return Embedder()
