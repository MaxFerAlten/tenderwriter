"""
TenderWriter — Dense Retriever (Vector Search via Qdrant)

Performs semantic similarity search using dense vector embeddings
stored in Qdrant collections.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from qdrant_client import QdrantClient, models

from app.config import settings
from app.rag.embedder import Embedder

logger = structlog.get_logger()


@dataclass
class DenseSearchResult:
    """A single result from dense vector search."""
    text: str
    score: float
    metadata: dict
    point_id: str


class DenseRetriever:
    """
    Dense retrieval using Qdrant vector database.

    Manages collections, indexing, and similarity search over
    document chunk embeddings.
    """

    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.client: QdrantClient | None = None
        self.collection_prefix = settings.qdrant_collection_prefix

    async def initialize(self):
        """Connect to Qdrant and ensure collections exist."""
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
        )
        logger.info("Connected to Qdrant", host=settings.qdrant_host, port=settings.qdrant_port)

        # Create default collections if they don't exist
        for collection_name in ["documents", "content_blocks"]:
            await self._ensure_collection(collection_name)

    async def _ensure_collection(self, name: str):
        """Create a Qdrant collection if it doesn't exist."""
        full_name = f"{self.collection_prefix}{name}"
        collections = self.client.get_collections().collections
        existing = [c.name for c in collections]

        if full_name not in existing:
            self.client.create_collection(
                collection_name=full_name,
                vectors_config=models.VectorParams(
                    size=self.embedder.dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection", collection=full_name)

    def index_chunks(
        self,
        texts: list[str],
        metadatas: list[dict],
        collection: str = "documents",
    ) -> list[str]:
        """
        Index a batch of text chunks into Qdrant.

        Returns a list of point IDs for each indexed chunk.
        """
        full_name = f"{self.collection_prefix}{collection}"
        embeddings = self.embedder.embed_batch(texts)
        point_ids = [str(uuid.uuid4()) for _ in texts]

        points = [
            models.PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={"text": text, **metadata},
            )
            for point_id, embedding, text, metadata in zip(
                point_ids, embeddings, texts, metadatas
            )
        ]

        # Batch upsert (Qdrant handles batching internally)
        self.client.upsert(collection_name=full_name, points=points)
        logger.info(
            "Indexed chunks into Qdrant",
            collection=full_name,
            count=len(points),
        )

        return point_ids

    def search(
        self,
        query: str,
        top_k: int | None = None,
        collection: str = "documents",
        filters: dict | None = None,
    ) -> list[DenseSearchResult]:
        """
        Search for similar chunks using dense vector similarity.

        Args:
            query: The search query text.
            top_k: Number of results to return.
            collection: Which Qdrant collection to search.
            filters: Optional metadata filters (e.g., {"doc_type": "proposal"}).

        Returns:
            List of DenseSearchResult ordered by similarity score (descending).
        """
        top_k = top_k or settings.rag_top_k_dense
        full_name = f"{self.collection_prefix}{collection}"

        query_embedding = self.embedder.embed_query(query)

        # Build Qdrant filter conditions
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value),
                        )
                    )
                else:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        )
                    )
            qdrant_filter = models.Filter(must=conditions)

        response = self.client.query_points(
            collection_name=full_name,
            query=query_embedding.tolist(),
            limit=top_k,
            query_filter=qdrant_filter,
        )

        search_results = [
            DenseSearchResult(
                text=hit.payload.get("text", ""),
                score=hit.score,
                metadata={k: v for k, v in hit.payload.items() if k != "text"},
                point_id=str(hit.id),
            )
            for hit in response.points
        ]

        logger.debug("Dense search complete", query_len=len(query), results=len(search_results))
        return search_results

    def delete_by_document(self, document_id: int, collection: str = "documents"):
        """Delete all vectors associated with a specific document."""
        full_name = f"{self.collection_prefix}{collection}"
        self.client.delete(
            collection_name=full_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for document", document_id=document_id)

    async def shutdown(self):
        """Close the Qdrant client connection."""
        if self.client:
            self.client.close()
