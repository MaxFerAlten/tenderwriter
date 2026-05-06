"""Unit tests for RAG retrieval baseline evaluation."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_module_loaders import load_service_test_module

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

_SERVICE_MODULE = load_service_test_module("app.services.rag_retrieval_evaluation")


class _FakeEngine:
    def __init__(self) -> None:
        self.queries: list[object] = []

    async def query(self, rag_query):
        self.queries.append(rag_query)
        return SimpleNamespace(
            sources=[
                {
                    "text": "Il fornitore deve garantire ISO/IEC 27001 e continuita operativa.",
                    "score": 0.91,
                    "metadata": {"page_number": 36, "procedure_key": "oscat"},
                    "retriever_sources": ["dense", "graph"],
                    "source_scores": {"dense": 0.7, "graph": 0.2},
                },
                {
                    "text": "Testo irrilevante.",
                    "score": 0.42,
                    "metadata": {"page": 8},
                    "retriever_sources": ["sparse"],
                },
            ],
        )


class _PageOffsetEngine:
    def __init__(self, page_number: int) -> None:
        self.page_number = page_number

    async def query(self, rag_query):
        return SimpleNamespace(
            sources=[
                {
                    "text": "La certificazione ISO/IEC 27001 e richiesta dal capitolato.",
                    "score": 0.88,
                    "metadata": {"page_number": self.page_number},
                    "retriever_sources": ["dense"],
                }
            ],
        )


class RagRetrievalEvaluationTests(unittest.IsolatedAsyncioTestCase):
    def test_load_evaluation_set_accepts_curated_list_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "evaluation_set.json"
            path.write_text(
                """
                [
                  {
                    "id": "Q001",
                    "query": "Quali certificazioni sono richieste?",
                    "expected_answer_keywords": ["ISO/IEC 27001"],
                    "source_pages": [36],
                    "difficulty": "easy"
                  }
                ]
                """,
                encoding="utf-8",
            )

            cases = _SERVICE_MODULE.load_retrieval_evaluation_set(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "Q001")
        self.assertEqual(cases[0].expected_answer_keywords, ("ISO/IEC 27001",))

    async def test_evaluate_retrieval_baseline_reports_recall_precision_and_pages(self) -> None:
        engine = _FakeEngine()
        cases = [
            _SERVICE_MODULE.RetrievalEvaluationCase(
                case_id="Q001",
                query="Quali certificazioni?",
                expected_answer_keywords=("ISO/IEC 27001", "non trovato"),
                source_pages=(36,),
                ontology_domain="CERTIFICAZIONI",
                difficulty="easy",
            ),
            _SERVICE_MODULE.RetrievalEvaluationCase(
                case_id="Q002",
                query="Quali penali?",
                expected_answer_keywords=("risoluzione",),
                source_pages=(99,),
                ontology_domain="PENALITA",
                difficulty="hard",
            ),
        ]

        report = await _SERVICE_MODULE.evaluate_retrieval_baseline(
            engine,
            cases,
            top_k=5,
            precision_k=3,
            filters={"doc_type": "tender"},
            tender_id=123,
            retrievers={"dense": True, "sparse": True, "graph": False},
            fusion_weights={"dense": 0.45, "sparse": 0.35, "graph": 0.15},
        )

        self.assertEqual(report.case_count, 2)
        self.assertEqual(report.recall_at_k, 0.5)
        self.assertEqual(report.precision_at_k, 0.25)
        self.assertEqual(report.source_page_hit_rate, 0.5)
        self.assertEqual(report.graph_source_count, 2)
        self.assertEqual(report.graph_case_count, 2)
        self.assertEqual(report.cases[0].hit_keyword_count, 1)
        self.assertEqual(report.cases[0].graph_source_count, 1)
        self.assertEqual(report.cases[0].retrieved_pages, (36, 8))
        self.assertEqual(report.cases[0].retrieved_sources[0]["source_scores"]["graph"], 0.2)
        self.assertGreaterEqual(report.average_latency_ms, 0.0)
        self.assertEqual(engine.queries[0].mode.value, "search")
        self.assertEqual(engine.queries[0].top_k, 5)
        self.assertEqual(engine.queries[0].tender_id, 123)
        self.assertEqual(engine.queries[0].filters, {"doc_type": "tender"})
        self.assertEqual(
            engine.queries[0].retrievers,
            {"dense": True, "sparse": True, "graph": False},
        )
        self.assertEqual(
            report.retrievers,
            {"dense": True, "sparse": True, "graph": False},
        )
        self.assertEqual(
            report.fusion_weights,
            {"dense": 0.45, "sparse": 0.35, "graph": 0.15},
        )

    async def test_evaluate_retrieval_baseline_disables_graph_by_default(self) -> None:
        engine = _FakeEngine()
        cases = [
            _SERVICE_MODULE.RetrievalEvaluationCase(
                case_id="Q001",
                query="Quali certificazioni?",
                expected_answer_keywords=("ISO/IEC 27001",),
            ),
        ]

        report = await _SERVICE_MODULE.evaluate_retrieval_baseline(engine, cases)

        self.assertEqual(
            engine.queries[0].retrievers,
            {"dense": True, "sparse": True, "graph": False},
        )
        self.assertEqual(
            report.retrievers,
            {"dense": True, "sparse": True, "graph": False},
        )

    async def test_evaluate_retrieval_baseline_adds_graph_ontology_filter_when_graph_enabled(
        self,
    ) -> None:
        engine = _FakeEngine()
        cases = [
            _SERVICE_MODULE.RetrievalEvaluationCase(
                case_id="Q001",
                query="Quali certificazioni?",
                expected_answer_keywords=("ISO/IEC 27001",),
                ontology_domain="CERTIFICAZIONI",
            ),
        ]

        await _SERVICE_MODULE.evaluate_retrieval_baseline(
            engine,
            cases,
            filters={"doc_type": "tender"},
            retrievers={"dense": True, "sparse": True, "graph": True},
        )

        self.assertEqual(
            engine.queries[0].filters,
            {"doc_type": "tender", "graph_ontology_domain": "CERTIFICAZIONI"},
        )

    async def test_evaluate_retrieval_baseline_reports_calibrated_page_hits(
        self,
    ) -> None:
        engine = _PageOffsetEngine(page_number=40)
        cases = [
            _SERVICE_MODULE.RetrievalEvaluationCase(
                case_id="Q001",
                query="Quali certificazioni?",
                expected_answer_keywords=("ISO/IEC 27001",),
                source_pages=(36,),
            ),
        ]

        report = await _SERVICE_MODULE.evaluate_retrieval_baseline(engine, cases)

        self.assertEqual(report.source_page_hit_rate, 1.0)
        self.assertEqual(report.exact_source_page_hit_rate, 0.0)
        self.assertTrue(report.cases[0].source_page_hit)
        self.assertFalse(report.cases[0].exact_source_page_hit)
        self.assertEqual(report.cases[0].matched_source_pages, (36,))


if __name__ == "__main__":
    unittest.main()
