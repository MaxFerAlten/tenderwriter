# ruff: noqa: E402
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

    async def test_graph_only_filters_are_not_sent_to_dense_or_sparse(self) -> None:
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
                text="Quali certificazioni sono richieste?",
                mode=QueryMode.SEARCH,
                tender_id=42,
                filters={
                    "doc_type": "tender",
                    "graph_ontology_domain": "CERTIFICAZIONI",
                },
            )
        )

        expected_vector_filters = {"doc_type": "tender", "tender_id": 42}
        self.assertEqual(dense.call_args.kwargs["filters"], expected_vector_filters)
        self.assertEqual(sparse.call_args.kwargs["filters"], expected_vector_filters)
        self.assertEqual(
            graph.await_args.kwargs["filters"],
            {
                "doc_type": "tender",
                "tender_id": 42,
                "graph_ontology_domain": "CERTIFICAZIONI",
            },
        )

    async def test_graph_enabled_retrieval_keeps_graph_candidates_for_rerank(self) -> None:
        engine = HybridRAGEngine()
        dense_items = [
            SimpleNamespace(text=f"dense-{index}", score=1.0, metadata={}) for index in range(5)
        ]
        sparse_items = [
            SimpleNamespace(text=f"sparse-{index}", score=1.0, metadata={}) for index in range(5)
        ]
        graph_items = [
            SimpleNamespace(text=f"graph-{index}", score=1.0, metadata={}) for index in range(5)
        ]
        engine.dense_retriever = SimpleNamespace(search=Mock(return_value=dense_items))
        engine.sparse_retriever = SimpleNamespace(search=Mock(return_value=sparse_items))
        engine.graph_retriever = SimpleNamespace(search=AsyncMock(return_value=graph_items))

        class RecordingFusion:
            def __init__(self) -> None:
                self.top_k = None

            def fuse(
                self,
                dense_results=None,
                sparse_results=None,
                graph_results=None,
                top_k=None,
            ):
                self.top_k = top_k
                fused = []
                for source_name, results in (
                    ("dense", dense_results or []),
                    ("sparse", sparse_results or []),
                    ("graph", graph_results or []),
                ):
                    fused.extend(
                        SimpleNamespace(
                            text=result["text"],
                            score=result["score"],
                            metadata=result["metadata"],
                            sources=[source_name],
                            source_scores={source_name: result["score"]},
                        )
                        for result in results
                    )
                return fused[:top_k]

        class RecordingReranker:
            def __init__(self) -> None:
                self.results = []

            def rerank(self, query, results, top_k=None):
                self.results = results
                return []

        fusion = RecordingFusion()
        reranker = RecordingReranker()
        engine.reranker = reranker

        with patch.object(engine, "_build_rank_fusion_for_query", return_value=fusion):
            await engine._retrieve_context_and_sources(
                RAGQuery(
                    text="Quali certificazioni sono richieste?",
                    mode=QueryMode.SEARCH,
                    top_k=5,
                    retrieval_top_k=5,
                    retrievers={"dense": True, "sparse": True, "graph": True},
                )
            )

        self.assertEqual(fusion.top_k, 15)
        self.assertTrue(
            any("graph" in result["sources"] for result in reranker.results),
            reranker.results,
        )

    async def test_graph_candidate_is_preserved_in_final_sources_after_rerank(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = SimpleNamespace(
            search=Mock(
                return_value=[
                    SimpleNamespace(text=f"dense-{index}", score=1.0, metadata={})
                    for index in range(3)
                ]
            )
        )
        engine.sparse_retriever = SimpleNamespace(
            search=Mock(
                return_value=[
                    SimpleNamespace(text=f"sparse-{index}", score=1.0, metadata={})
                    for index in range(3)
                ]
            )
        )
        engine.graph_retriever = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        text="graph-critical-relationship",
                        score=1.0,
                        metadata={"source": "knowledge_graph"},
                    )
                ]
            )
        )

        class FixedFusion:
            def fuse(self, **_kwargs):
                return [
                    SimpleNamespace(
                        text="dense-0",
                        score=0.9,
                        metadata={},
                        sources=["dense"],
                        source_scores={"dense": 0.9},
                    ),
                    SimpleNamespace(
                        text="dense-1",
                        score=0.8,
                        metadata={},
                        sources=["dense"],
                        source_scores={"dense": 0.8},
                    ),
                    SimpleNamespace(
                        text="sparse-0",
                        score=0.7,
                        metadata={},
                        sources=["sparse"],
                        source_scores={"sparse": 0.7},
                    ),
                    SimpleNamespace(
                        text="graph-critical-relationship",
                        score=0.6,
                        metadata={"source": "knowledge_graph"},
                        sources=["graph"],
                        source_scores={"graph": 0.6},
                    ),
                ]

        class FixedReranker:
            def rerank(self, query, results, top_k=None):
                del query
                return [
                    SimpleNamespace(
                        text=result["text"],
                        score=1.0 - (index / 10),
                        metadata=result["metadata"],
                        sources=result["sources"],
                        source_scores=result["source_scores"],
                    )
                    for index, result in enumerate(results[:top_k])
                ]

        engine.reranker = FixedReranker()

        with patch.object(engine, "_build_rank_fusion_for_query", return_value=FixedFusion()):
            retrieved = await engine._retrieve_context_and_sources(
                RAGQuery(
                    text="Quali sono i punti critici?",
                    mode=QueryMode.SEARCH,
                    top_k=3,
                    retrieval_top_k=3,
                    retrievers={"dense": True, "sparse": True, "graph": True},
                )
            )

        self.assertEqual(len(retrieved.sources), 3)
        self.assertTrue(
            any("graph" in source["retriever_sources"] for source in retrieved.sources),
            retrieved.sources,
        )

    async def test_graph_search_prefers_tender_scoped_nodes_with_tender_filter(self) -> None:
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
            patch.object(retriever, "_search_evidence_chunks", AsyncMock(return_value=[])),
            patch.object(
                retriever,
                "_search_tenders",
                AsyncMock(return_value=[tender_result]),
            ) as tender_mock,
            patch.object(
                retriever,
                "_search_projects",
                AsyncMock(return_value=[]),
            ) as project_mock,
            patch.object(
                retriever,
                "_search_team_members",
                AsyncMock(return_value=[]),
            ) as member_mock,
            patch.object(
                retriever,
                "_search_requirements",
                AsyncMock(return_value=[requirement_result]),
            ) as requirement_mock,
        ):
            results = await retriever.search("riassumi la gara", top_k=5, filters={"tender_id": 42})

        tender_mock.assert_awaited_once()
        requirement_mock.assert_awaited_once()
        project_mock.assert_not_awaited()
        member_mock.assert_not_awaited()
        self.assertEqual([item.entity_type for item in results], ["Tender", "Requirement"])

    async def test_graph_search_uses_evidence_chunks_for_ontology_filter(self) -> None:
        retriever = GraphRetriever()
        evidence_result = GraphSearchResult(
            text="Evidence: ISO 27001 richiesta",
            score=0.92,
            metadata={
                "source": "knowledge_graph",
                "entity_type": "EvidenceChunk",
                "ontology_domain": "compliance",
                "page_number": 36,
            },
            entity_type="EvidenceChunk",
            relationships=[],
        )

        with (
            patch.object(
                retriever,
                "_search_evidence_chunks",
                AsyncMock(return_value=[evidence_result]),
            ) as evidence_mock,
            patch.object(retriever, "_search_projects", AsyncMock(return_value=[])) as project_mock,
            patch.object(
                retriever,
                "_search_team_members",
                AsyncMock(return_value=[]),
            ) as member_mock,
            patch.object(retriever, "_search_requirements", AsyncMock(return_value=[])),
        ):
            results = await retriever.search(
                "Quali certificazioni?",
                top_k=5,
                filters={"graph_ontology_domain": "CERTIFICAZIONI"},
            )

        evidence_mock.assert_awaited_once()
        project_mock.assert_not_awaited()
        member_mock.assert_not_awaited()
        self.assertEqual([item.entity_type for item in results], ["EvidenceChunk"])

    def test_graph_maps_gold_domains_to_internal_ontology_domains(self) -> None:
        retriever = GraphRetriever()

        self.assertEqual(
            retriever._ontology_filter_domains({"graph_ontology_domain": "CERTIFICAZIONI"}),
            {"compliance"},
        )
        self.assertEqual(
            retriever._ontology_filter_domains({"graph_ontology_domain": "SLA_PENALITA"}),
            {"tecnico", "contrattuale"},
        )

    def test_graph_requirement_result_filters_by_ontology_domain(self) -> None:
        retriever = GraphRetriever()
        requirement = {
            "id": "req-1",
            "text": "Il concorrente deve possedere la certificazione ISO 27001.",
            "category": "certifications",
            "priority": "high",
            "tender_id": "42",
            "page_number": 36,
            "source_document_ref": "tenders/42/capitolato.pdf",
        }

        result = retriever._build_requirement_result(
            requirement,
            tender={"title": "Gara Toscana"},
            ontology_domains={"compliance"},
        )
        rejected = retriever._build_requirement_result(
            requirement,
            tender={"title": "Gara Toscana"},
            ontology_domains={"tecnico"},
        )

        self.assertIsNotNone(result)
        self.assertIsNone(rejected)
        assert result is not None
        self.assertEqual(result.metadata["ontology_domain"], "compliance")
        self.assertEqual(result.metadata["page_number"], 36)
        self.assertEqual(result.metadata["source_document_ref"], "tenders/42/capitolato.pdf")

    def test_graph_evidence_chunk_result_filters_by_ontology_domain(self) -> None:
        retriever = GraphRetriever()
        chunk = {
            "id": "chunk-1",
            "text": "La certificazione ISO/IEC 27001 deve essere mantenuta.",
            "doc_type": "tender",
            "tender_id": 42,
            "page_number": 36,
            "source_document_ref": "tenders/42/capitolato.pdf",
            "ontology_domain": "compliance",
            "ontology_subdomain": "certificazioni",
        }

        result = retriever._build_evidence_chunk_result(chunk, ontology_domains={"compliance"})
        rejected = retriever._build_evidence_chunk_result(chunk, ontology_domains={"tecnico"})

        self.assertIsNotNone(result)
        self.assertIsNone(rejected)
        assert result is not None
        self.assertEqual(result.entity_type, "EvidenceChunk")
        self.assertEqual(result.metadata["page_number"], 36)

    def test_graph_query_keywords_remove_generic_terms_and_add_domain_terms(self) -> None:
        retriever = GraphRetriever()

        keywords = retriever._query_keywords(
            "Quali certificazioni di qualità sono obbligatorie per il Fornitore?",
            ontology_domains={"compliance"},
        )

        self.assertIn("certificazioni", keywords)
        self.assertIn("iso", keywords)
        self.assertNotIn("fornitore", keywords)
        self.assertNotIn("quali", keywords)
        self.assertGreater(
            retriever._keyword_overlap(
                "La certificazione ISO 27001 deve essere mantenuta.",
                keywords,
            ),
            0,
        )
        self.assertEqual(retriever._keyword_overlap("Testo generico sul fornitore.", keywords), 0)


if __name__ == "__main__":
    unittest.main()
