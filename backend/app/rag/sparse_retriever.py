"""
TenderWriter — Sparse Retriever (BM25 Keyword Search)

Performs keyword-based retrieval using the BM25 algorithm.
Chunks and their BM25 tokens are stored in PostgreSQL for persistence.
The BM25 index is rebuilt on startup and incrementally updated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from rank_bm25 import BM25Okapi

from app.config import settings

logger = structlog.get_logger()


# Common English stop words to filter out
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "to", "was", "were", "will", "with", "this", "but", "they",
    "have", "had", "what", "when", "where", "who", "which", "their",
    "there", "been", "would", "could", "should", "can", "do", "does",
    "did", "not", "no", "if", "so", "than", "then", "these", "those",
    "our", "we", "you", "your", "my", "me", "him", "her", "she",
}


@dataclass
class SparseSearchResult:
    """A single result from BM25 search."""
    text: str
    score: float
    metadata: dict
    chunk_index: int


class SparseRetriever:
    """
    Sparse retrieval using BM25 (Best Matching 25).

    Maintains an in-memory BM25 index over tokenized document chunks.
    The index supports domain-specific terminology that dense embeddings
    might miss (technical specs, model numbers, certification codes, etc.).
    """

    def __init__(self):
        self._corpus_texts: list[str] = []
        self._corpus_metadata: list[dict] = []
        self._tokenized_corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25 indexing.

        Applies lowercasing, punctuation removal, and stop word filtering.
        Keeps alphanumeric tokens and domain-specific patterns (e.g., ISO-9001).
        """
        text = text.lower()
        # Keep alphanumeric and hyphens (for codes like ISO-9001, PMP, etc.)
        tokens = re.findall(r'\b[a-z0-9][\w-]*\b', text)
        # Filter stop words but keep short technical tokens (e.g., "ai", "ml")
        tokens = [t for t in tokens if t not in STOP_WORDS or len(t) <= 2]
        return tokens

    def build_index(self, texts: list[str], metadatas: list[dict]):
        """
        Build or rebuild the BM25 index from a corpus of texts.

        Args:
            texts: List of chunk texts.
            metadatas: List of metadata dicts, one per chunk.
        """
        self._corpus_texts = texts
        self._corpus_metadata = metadatas
        self._tokenized_corpus = [self._tokenize(t) for t in texts]

        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
            logger.info("BM25 index built", corpus_size=len(texts))
        else:
            self._bm25 = None
            logger.warning("BM25 index is empty — no documents to index")

    def add_chunks(self, texts: list[str], metadatas: list[dict]):
        """
        Incrementally add chunks to the existing BM25 index.

        Note: BM25Okapi doesn't support true incremental updates,
        so we rebuild the full index. For large corpora, consider
        periodic batch rebuilds in a background task.
        """
        self._corpus_texts.extend(texts)
        self._corpus_metadata.extend(metadatas)
        self._tokenized_corpus.extend([self._tokenize(t) for t in texts])

        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
            logger.debug("BM25 index updated", new_chunks=len(texts), total=len(self._corpus_texts))

    def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[SparseSearchResult]:
        """
        Search the BM25 index for relevant chunks.

        Args:
            query: The search query text.
            top_k: Number of results to return.
            filters: Optional metadata filters (applied post-retrieval).

        Returns:
            List of SparseSearchResult ordered by BM25 score (descending).
        """
        if self._bm25 is None or not self._corpus_texts:
            logger.warning("BM25 search called but index is empty")
            return []

        top_k = top_k or settings.rag_top_k_sparse
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Get top-k indices
        scored_indices = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        results: list[SparseSearchResult] = []
        for idx, score in scored_indices:
            if score <= 0:
                continue

            metadata = self._corpus_metadata[idx]

            # Apply post-retrieval filters
            if filters:
                if not self._matches_filters(metadata, filters):
                    continue

            results.append(
                SparseSearchResult(
                    text=self._corpus_texts[idx],
                    score=float(score),
                    metadata=metadata,
                    chunk_index=idx,
                )
            )

            if len(results) >= top_k:
                break

        logger.debug("BM25 search complete", query_tokens=len(query_tokens), results=len(results))
        return results

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        """Check if a chunk's metadata matches the given filters."""
        for key, value in filters.items():
            meta_value = metadata.get(key)
            if meta_value is None:
                return False
            if isinstance(value, list):
                if meta_value not in value:
                    return False
            elif meta_value != value:
                return False
        return True

    def remove_by_document(self, document_id: int):
        """Remove all chunks belonging to a specific document and rebuild."""
        new_texts = []
        new_metas = []
        for text, meta in zip(self._corpus_texts, self._corpus_metadata):
            if meta.get("document_id") != document_id:
                new_texts.append(text)
                new_metas.append(meta)

        self.build_index(new_texts, new_metas)
        logger.info("Removed document from BM25 index", document_id=document_id)

    @property
    def corpus_size(self) -> int:
        """Number of chunks in the index."""
        return len(self._corpus_texts)
