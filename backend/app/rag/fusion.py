"""
TenderWriter — Reciprocal Rank Fusion (RRF)

Merges ranked result lists from multiple retrievers (dense, sparse, graph)
into a single unified ranking using the RRF formula.

RRF is robust and doesn't require score normalization across different
retrieval methods.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.config import settings

logger = structlog.get_logger()


@dataclass
class FusedResult:
    """A single result after rank fusion from multiple sources."""
    text: str
    score: float
    metadata: dict
    sources: list[str]  # Which retrievers contributed this result


class RankFusion:
    """
    Reciprocal Rank Fusion (RRF) for combining ranked lists.

    Formula: score(d) = Σ (weight_i / (k + rank_i(d)))

    Where:
    - k is a constant (default 60) that controls how much lower-ranked
      results contribute to the final score
    - weight_i is the per-retriever importance weight
    - rank_i(d) is the rank of document d in retriever i's result list
    """

    def __init__(
        self,
        k: int | None = None,
        dense_weight: float | None = None,
        sparse_weight: float | None = None,
        graph_weight: float | None = None,
    ):
        self.k = k or settings.rag_rrf_k
        self.dense_weight = dense_weight or settings.rag_dense_weight
        self.sparse_weight = sparse_weight or settings.rag_sparse_weight
        self.graph_weight = graph_weight or settings.rag_graph_weight

    def fuse(
        self,
        dense_results: list[dict] | None = None,
        sparse_results: list[dict] | None = None,
        graph_results: list[dict] | None = None,
        top_k: int | None = None,
    ) -> list[FusedResult]:
        """
        Combine results from multiple retrievers using RRF.

        Each result dict should have at minimum {"text": str, "metadata": dict}.
        Results are identified by their text content for deduplication.

        Args:
            dense_results: Results from vector search.
            sparse_results: Results from BM25 search.
            graph_results: Results from knowledge graph.
            top_k: Number of fused results to return.

        Returns:
            List of FusedResult sorted by fused score (descending).
        """
        dense_results = dense_results or []
        sparse_results = sparse_results or []
        graph_results = graph_results or []

        # Track scores and sources per unique result
        # Key: normalized text (first 200 chars for dedup)
        score_map: dict[str, dict] = {}

        def _dedup_key(text: str) -> str:
            """Create a deduplication key from text."""
            return text.strip().lower()[:200]

        # Process each retriever's results
        retriever_configs = [
            (dense_results, self.dense_weight, "dense"),
            (sparse_results, self.sparse_weight, "sparse"),
            (graph_results, self.graph_weight, "graph"),
        ]

        for results, weight, source_name in retriever_configs:
            for rank, result in enumerate(results, start=1):
                text = result.get("text", "")
                key = _dedup_key(text)

                if not key:
                    continue

                rrf_score = weight / (self.k + rank)

                if key not in score_map:
                    score_map[key] = {
                        "text": text,
                        "score": 0.0,
                        "metadata": result.get("metadata", {}),
                        "sources": [],
                    }

                score_map[key]["score"] += rrf_score
                if source_name not in score_map[key]["sources"]:
                    score_map[key]["sources"].append(source_name)

                # Merge metadata from multiple sources
                for mk, mv in result.get("metadata", {}).items():
                    if mk not in score_map[key]["metadata"]:
                        score_map[key]["metadata"][mk] = mv

        # Sort by fused score
        sorted_results = sorted(score_map.values(), key=lambda x: x["score"], reverse=True)

        # Apply top_k
        if top_k:
            sorted_results = sorted_results[:top_k]

        fused = [
            FusedResult(
                text=r["text"],
                score=r["score"],
                metadata=r["metadata"],
                sources=r["sources"],
            )
            for r in sorted_results
        ]

        logger.debug(
            "Rank fusion complete",
            dense=len(dense_results),
            sparse=len(sparse_results),
            graph=len(graph_results),
            fused=len(fused),
        )

        return fused
