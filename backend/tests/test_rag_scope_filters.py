"""Regression tests for tender-scoped retrieval filters."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery
from app.rag.graph_retriever import GraphRetriever, GraphSearchResult


class RagScopeFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_context_merges_tender_id_into_retriever_filters(self) -> None:
        engine = HybridRAGEngine()
        dense = Mock(return_value=[])
        sparse = Mock(return_value=[])
        graph = AsyncMock(return_value=[])
        engine.dense_retriever = SimpleNamespace(search=dense)
        engine.sparse_retriever = SimpleNamespace(search=sparse)
        engine.graph_retriever = SimpleNamespace(search=graph)
        engine.fusion = SimpleNamespace(fuse=lambda **_: [])
        engine.reranker = SimpleNamespace(rerank=lambda **_: [])

        await engine._retrieve_context_and_sources(
            RAGQuery(
                text="Riassumi la gara",
                mode=QueryMode.SEARCH,
                tender_id=42,
                filters={"doc_type": "tender"},
            )
        )

        expected_filters = {"doc_type": "tender", "tender_id": 42}
        self.assertEqual(dense.call_args.kwargs["filters"], expected_filters)
        self.assertEqual(sparse.call_args.kwargs["filters"], expected_filters)
        self.assertEqual(graph.await_args.kwargs["filters"], expected_filters)

    async def test_graph_search_prefers_tender_scoped_nodes_when_tender_filter_is_present(self) -> None:
        retriever = GraphRetriever()
        tender_result = GraphSearchResult(
            text="Tender: Gara Toscana",
            score=0.95,
            metadata={"source": "knowledge_graph", "tender_id": "42"},
            entity_type="Tender",
            relationships=[],
        )
        requirement_result = GraphSearchResult(
            text="Requirement: Presentare ISO 27001",
            score=0.85,
            metadata={"source": "knowledge_graph", "tender_id": "42"},
            entity_type="Requirement",
            relationships=[],
        )

        with (
            patch.object(retriever, "_search_tenders", AsyncMock(return_value=[tender_result])) as tender_mock,
            patch.object(retriever, "_search_projects", AsyncMock(return_value=[])) as project_mock,
            patch.object(retriever, "_search_team_members", AsyncMock(return_value=[])) as member_mock,
            patch.object(retriever, "_search_requirements", AsyncMock(return_value=[requirement_result])) as requirement_mock,
        ):
            results = await retriever.search("riassumi la gara", top_k=5, filters={"tender_id": 42})

        tender_mock.assert_awaited_once()
        requirement_mock.assert_awaited_once()
        project_mock.assert_not_awaited()
        member_mock.assert_not_awaited()
        self.assertEqual([item.entity_type for item in results], ["Tender", "Requirement"])


if __name__ == "__main__":
    unittest.main()
