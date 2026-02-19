"""
TenderWriter — Semantic Chunker

Splits documents into semantically coherent chunks by detecting topic shifts
using embedding similarity between consecutive sentences/paragraphs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ChunkMetadata:
    """Metadata attached to each chunk."""
    document_id: int | None = None
    source_file: str = ""
    section_title: str = ""
    page_number: int | None = None
    chunk_index: int = 0
    doc_type: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class TextChunk:
    """A chunk of text with metadata."""
    text: str
    metadata: ChunkMetadata


class SemanticChunker:
    """
    Splits text into chunks based on semantic similarity between sentences.

    Uses a sliding window to detect topic boundaries by measuring cosine
    similarity of embeddings between consecutive groups of sentences.
    When similarity drops below a threshold, a chunk boundary is inserted.

    Falls back to fixed-size chunking if embeddings are unavailable.
    """

    def __init__(
        self,
        embedder=None,
        min_chunk_size: int = 200,
        max_chunk_size: int = 1500,
        similarity_threshold: float = 0.5,
        overlap_sentences: int = 1,
    ):
        self.embedder = embedder
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.similarity_threshold = similarity_threshold
        self.overlap_sentences = overlap_sentences

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, vec_a, vec_b) -> float:
        """Compute cosine similarity between two vectors."""
        import numpy as np
        dot = np.dot(vec_a, vec_b)
        norm = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
        return float(dot / norm) if norm > 0 else 0.0

    def chunk_text(
        self,
        text: str,
        metadata: ChunkMetadata | None = None,
    ) -> list[TextChunk]:
        """
        Split text into semantically coherent chunks.

        If an embedder is available, uses semantic similarity to detect
        topic boundaries. Otherwise, falls back to fixed-size chunking.
        """
        if not text or not text.strip():
            return []

        metadata = metadata or ChunkMetadata()
        sentences = self._split_sentences(text)

        if len(sentences) <= 1:
            return [TextChunk(text=text.strip(), metadata=metadata)]

        # If no embedder, use fixed-size chunking
        if self.embedder is None:
            return self._fixed_size_chunk(sentences, metadata)

        return self._semantic_chunk(sentences, metadata)

    def _semantic_chunk(
        self,
        sentences: list[str],
        base_metadata: ChunkMetadata,
    ) -> list[TextChunk]:
        """Chunk using embedding similarity to detect topic shifts."""
        import numpy as np

        # Embed all sentences in batch
        embeddings = self.embedder.embed_batch(sentences)

        # Find split points by measuring similarity between consecutive sentences
        split_points: list[int] = []
        for i in range(1, len(sentences)):
            sim = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if sim < self.similarity_threshold:
                split_points.append(i)

        # Build chunks from split points
        chunks: list[TextChunk] = []
        start = 0
        for split_idx in split_points:
            chunk_text = " ".join(sentences[start:split_idx])

            # Enforce min/max size constraints
            if len(chunk_text) < self.min_chunk_size and chunks:
                # Merge with previous chunk if too small
                prev = chunks[-1]
                prev.text = prev.text + " " + chunk_text
                # Enforce max size — if merged chunk too big, keep separate
                if len(prev.text) > self.max_chunk_size:
                    prev.text = prev.text[: -len(chunk_text) - 1]
                    meta = ChunkMetadata(**{
                        k: v for k, v in base_metadata.__dict__.items()
                    })
                    meta.chunk_index = len(chunks)
                    chunks.append(TextChunk(text=chunk_text, metadata=meta))
            else:
                meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
                meta.chunk_index = len(chunks)
                chunks.append(TextChunk(text=chunk_text, metadata=meta))

            start = split_idx

        # Remaining text
        if start < len(sentences):
            remaining = " ".join(sentences[start:])
            if remaining.strip():
                meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
                meta.chunk_index = len(chunks)
                chunks.append(TextChunk(text=remaining, metadata=meta))

        # Final pass: split any chunks that exceed max_chunk_size
        final_chunks = []
        for chunk in chunks:
            if len(chunk.text) > self.max_chunk_size:
                sub_chunks = self._split_oversized(chunk.text, base_metadata, len(final_chunks))
                final_chunks.extend(sub_chunks)
            else:
                chunk.metadata.chunk_index = len(final_chunks)
                final_chunks.append(chunk)

        logger.debug("Semantic chunking complete", num_chunks=len(final_chunks))
        return final_chunks

    def _fixed_size_chunk(
        self,
        sentences: list[str],
        base_metadata: ChunkMetadata,
    ) -> list[TextChunk]:
        """Fallback: chunk by accumulating sentences up to max_chunk_size."""
        chunks: list[TextChunk] = []
        current_sentences: list[str] = []
        current_len = 0

        for sentence in sentences:
            if current_len + len(sentence) > self.max_chunk_size and current_sentences:
                text = " ".join(current_sentences)
                meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
                meta.chunk_index = len(chunks)
                chunks.append(TextChunk(text=text, metadata=meta))

                # Overlap: carry forward last N sentences
                current_sentences = current_sentences[-self.overlap_sentences:]
                current_len = sum(len(s) for s in current_sentences)

            current_sentences.append(sentence)
            current_len += len(sentence)

        # Final chunk
        if current_sentences:
            text = " ".join(current_sentences)
            meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
            meta.chunk_index = len(chunks)
            chunks.append(TextChunk(text=text, metadata=meta))

        logger.debug("Fixed-size chunking complete", num_chunks=len(chunks))
        return chunks

    def _split_oversized(
        self,
        text: str,
        base_metadata: ChunkMetadata,
        start_index: int,
    ) -> list[TextChunk]:
        """Split text that exceeds max_chunk_size into smaller pieces."""
        words = text.split()
        chunks: list[TextChunk] = []
        current_words: list[str] = []
        current_len = 0

        for word in words:
            if current_len + len(word) + 1 > self.max_chunk_size and current_words:
                chunk_text = " ".join(current_words)
                meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
                meta.chunk_index = start_index + len(chunks)
                chunks.append(TextChunk(text=chunk_text, metadata=meta))
                current_words = []
                current_len = 0

            current_words.append(word)
            current_len += len(word) + 1

        if current_words:
            chunk_text = " ".join(current_words)
            meta = ChunkMetadata(**{k: v for k, v in base_metadata.__dict__.items()})
            meta.chunk_index = start_index + len(chunks)
            chunks.append(TextChunk(text=chunk_text, metadata=meta))

        return chunks
