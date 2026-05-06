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
    source_scores: dict[str, float] = None

    def __post_init__(self):
        if self.source_scores is None:
            self.source_scores = {}


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
        mmr_lambda: float = 0.7,
    ) -> list[RerankedResult]:
        """
        Re-rank results using the cross-encoder, optionally with MMR diversification.

        Args:
            query: The original search query.
            results: List of candidate results with "text", "score",
                     "metadata", and "sources" keys.
            top_k: Number of re-ranked results to return.
            mmr_lambda: MMR lambda parameter (0=max diversity, 1=max relevance).
                       If < 1.0, applies MMR diversification.

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
        for result, ce_score in zip(results, scores, strict=False):
            reranked.append(
                RerankedResult(
                    text=result["text"],
                    score=float(ce_score),
                    original_score=result.get("score", 0.0),
                    metadata=result.get("metadata", {}),
                    sources=result.get("sources", []),
                    source_scores=result.get("source_scores", {}),
                )
            )

        # Sort by cross-encoder score
        reranked.sort(key=lambda x: x.score, reverse=True)

        # Apply MMR diversification if lambda < 1.0
        if mmr_lambda < 1.0 and len(reranked) > 2:
            reranked = self._mmr_diversify(query, reranked, mmr_lambda, top_k)

        # Take top_k
        reranked = reranked[:top_k]

        logger.debug(
            "Re-ranking complete",
            candidates=len(results),
            returned=len(reranked),
            top_score=reranked[0].score if reranked else None,
        )

        return reranked

    def _mmr_diversify(
        self,
        query: str,
        results: list[RerankedResult],
        lambda_param: float = 0.7,
        top_k: int = 6,
    ) -> list[RerankedResult]:
        """Apply Maximal Marginal Relevance for result diversification."""
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer

            if not results:
                return results

            # Embed all texts
            embedder = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            texts = [r.text for r in results]
            embeddings = embedder.encode(texts, show_progress_bar=False)

            # Normalize embeddings for cosine similarity
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1
            embeddings = embeddings / norms

            # MMR selection
            selected = []
            selected_indices = []
            remaining_indices = list(range(len(results)))

            while len(selected) < top_k and remaining_indices:
                best_idx = None
                best_mmr = float("-inf")

                for idx in remaining_indices:
                    relevance = results[idx].score
                    if selected_indices:
                        # Calculate redundancy (max similarity to selected)
                        selected_embs = embeddings[selected_indices]
                        sims = np.dot(embeddings[idx], selected_embs.T)
                        redundancy = np.max(sims)
                    else:
                        redundancy = 0

                    mmr = lambda_param * relevance - (1 - lambda_param) * redundancy

                    if mmr > best_mmr:
                        best_mmr = mmr
                        best_idx = idx

                if best_idx is not None:
                    selected.append(results[best_idx])
                    selected_indices.append(best_idx)
                    remaining_indices.remove(best_idx)

            logger.debug(
                "MMR diversification applied", original=len(results), diversified=len(selected)
            )
            return selected
        except Exception as e:
            logger.warning("MMR diversification failed, using original order", error=str(e))
            return results


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Singleton factory for the reranker instance."""
    return Reranker()
