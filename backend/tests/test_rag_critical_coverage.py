# ruff: noqa: E402
"""Tests for Markdown-driven critical tender coverage retrieval expansion."""

from __future__ import annotations

import os
import unittest

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

from app.rag.engine import HybridRAGEngine
from app.rag.internal_prompting import load_retrieval_query_variants


class RagCriticalCoverageTests(unittest.TestCase):
    def test_retrieval_query_variants_load_from_markdown_assets(self) -> None:
        italian_variants = load_retrieval_query_variants(
            "retrieval-critical-coverage",
            language="it",
        )
        english_variants = load_retrieval_query_variants(
            "retrieval-critical-coverage",
            language="en",
        )

        self.assertTrue(any("qualificazione ACN" in query for query in italian_variants))
        self.assertTrue(any("ACN qualification" in query for query in english_variants))
        self.assertTrue(any("OSCAT CIG" in query for query in italian_variants))
        self.assertTrue(any("OSCAT duration" in query for query in english_variants))
        self.assertTrue(any("OSCAT luogo" in query for query in italian_variants))
        self.assertTrue(any("OSCAT location" in query for query in english_variants))

    def test_structured_tender_overview_expands_retrieval_queries(self) -> None:
        engine = HybridRAGEngine()

        queries = engine._retrieval_queries_for("Analizza questa gara e dimmi punti critici")

        self.assertTrue(any("qualificazione ACN" in query for query in queries))
        self.assertTrue(any("CCTT" in query for query in queries))
        self.assertTrue(any("CO-LO-KW" in query for query in queries))
        self.assertTrue(any("art. 1456" in query for query in queries))

    def test_generic_tender_overview_does_not_expand_oscat_variants(self) -> None:
        engine = HybridRAGEngine()

        queries = engine._retrieval_queries_for("Analizza questa gara e dimmi punti critici")

        self.assertFalse(any("OSCAT" in query for query in queries))

    def test_english_tender_overview_uses_english_retrieval_variants(self) -> None:
        engine = HybridRAGEngine()

        queries = engine._retrieval_queries_for("Give me a complete overview of this tender")

        self.assertTrue(any("ACN qualification" in query for query in queries))
        self.assertFalse(any("qualificazione ACN" in query for query in queries))

    def test_oscat_tender_overview_expands_to_protected_fact_queries(self) -> None:
        engine = HybridRAGEngine()

        queries = engine._retrieval_queries_for("Descrivi la gara OSCAT in modo completo")

        self.assertTrue(any("OSCAT CIG" in query for query in queries))
        self.assertTrue(any("OSCAT durata" in query for query in queries))
        self.assertTrue(any("OSCAT importo" in query for query in queries))
        self.assertTrue(any("OSCAT luogo" in query for query in queries))

    def test_non_tender_query_does_not_expand_retrieval_queries(self) -> None:
        engine = HybridRAGEngine()

        queries = engine._retrieval_queries_for("Spiega cos'e una matrice RACI")

        self.assertEqual(queries, ("Spiega cos'e una matrice RACI",))

    def test_generic_tender_concept_query_does_not_expand_retrieval_queries(self) -> None:
        engine = HybridRAGEngine()
        query = "Spiega cos'e una procedura aperta di gara"

        queries = engine._retrieval_queries_for(query)

        self.assertFalse(engine._query_requests_broad_summary(query))
        self.assertEqual(queries, (query,))

    def test_generic_tender_concept_variants_do_not_expand_retrieval_queries(self) -> None:
        engine = HybridRAGEngine()
        queries = (
            "Spiega la procedura aperta di gara",
            "Descrivi il criterio di aggiudicazione in una gara pubblica",
        )

        for query in queries:
            with self.subTest(query=query):
                self.assertFalse(engine._query_requests_broad_summary(query))
                self.assertEqual(engine._retrieval_queries_for(query), (query,))


def test_generic_tender_overview_expands_only_base_variants() -> None:
    from app.rag.engine import HybridRAGEngine

    engine = HybridRAGEngine()
    queries = engine._retrieval_queries_for("Analizza questa gara e dimmi i punti critici")
    joined = " ".join(queries)
    assert "identificativo procedura" in joined
    assert "importo base" in joined
    assert "OSCAT" not in joined and "CCTT" not in joined and "RTPC" not in joined


def test_oscat_profile_adds_oscat_variants_when_requested() -> None:
    from app.rag.engine import HybridRAGEngine
    from app.rag.procedure_profiles import OSCAT_SCT_TOSCANA_PROFILE

    engine = HybridRAGEngine()
    queries = engine._retrieval_queries_for(
        "Descrivi in modo completo la gara OSCAT",
        active_profiles=(OSCAT_SCT_TOSCANA_PROFILE,),
    )
    joined = " ".join(queries)
    assert "OSCAT CIG" in joined
    assert "OSCAT durata" in joined or "OSCAT duration" in joined


if __name__ == "__main__":
    unittest.main()
