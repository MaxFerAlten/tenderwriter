"""
TenderWriter — Cross-Encoder Re-Ranker

Re-ranks fused retrieval results using a cross-encoder model that
jointly encodes the query and each candidate passage. This provides
much more accurate relevance scoring than embedding-based similarity
at the cost of higher latency (applied only to top-N candidates).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import structlog

from app.config import settings

logger = structlog.get_logger()


@dataclass
class RerankedResult:
    """A result after cross-encoder re-ranking."""
    text: str
    score: float
    original_score: float
    metadata: dict
    sources: list[str]


class Reranker:
    """
    Cross-encoder re-ranker using sentence-transformers CrossEncoder.

    Takes the top-N results from rank fusion and re-scores them
    using a cross-encoder that considers query-passage interaction
    at the token level.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.reranker_model
        self._model = None

    @property
    def model(self):
        """Lazy-load the cross-encoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("Loading re-ranker model", model=self.model_name)
            self._model = CrossEncoder(self.model_name)
            logger.info("Re-ranker model loaded")
        return self._model

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int | None = None,
    ) -> list[RerankedResult]:
        """
        Re-rank results using the cross-encoder.

        Args:
            query: The original search query.
            results: List of candidate results with "text", "score",
                     "metadata", and "sources" keys.
            top_k: Number of re-ranked results to return.

        Returns:
            List of RerankedResult sorted by cross-encoder score (descending).
        """
        top_k = top_k or settings.rag_top_k_final

        if not results:
            return []

        # Build query-passage pairs for the cross-encoder
        pairs = [(query, r["text"]) for r in results]

        # Score all pairs
        scores = self.model.predict(pairs, show_progress_bar=False)

        # Combine with original results
        reranked = []
        for result, ce_score in zip(results, scores):
            reranked.append(
                RerankedResult(
                    text=result["text"],
                    score=float(ce_score),
                    original_score=result.get("score", 0.0),
                    metadata=result.get("metadata", {}),
                    sources=result.get("sources", []),
                )
            )

        # Sort by cross-encoder score
        reranked.sort(key=lambda x: x.score, reverse=True)

        # Take top_k
        reranked = reranked[:top_k]

        logger.debug(
            "Re-ranking complete",
            candidates=len(results),
            returned=len(reranked),
            top_score=reranked[0].score if reranked else None,
        )

        return reranked


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Singleton factory for the reranker instance."""
    return Reranker()
