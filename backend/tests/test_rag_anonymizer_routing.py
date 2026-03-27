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

from app.rag.engine import (
    AnonymizerUnavailableError,
    HybridRAGEngine,
    LLMRoute,
    QueryMode,
    RAGQuery,
)
from app.rag.generator import GenerationResult


class _EmptyRetriever:
    def search(self, **_kwargs):
        return []


class _EmptyGraphRetriever:
    async def search(self, **_kwargs):
        return []


class _FakeFusion:
    def fuse(self, **_kwargs):
        return [
            SimpleNamespace(
                text="Mario Rossi guida il progetto.",
                score=0.91,
                metadata={"document_id": "doc-1"},
                sources=["dense"],
            )
        ]


class _FakeReranker:
    def rerank(self, **_kwargs):
        return [
            {
                "text": "Mario Rossi guida il progetto.",
                "score": 0.91,
                "metadata": {"document_id": "doc-1"},
            }
        ]


class HybridRAGAnonymizerRoutingTests(unittest.IsolatedAsyncioTestCase):
    def _build_engine(self) -> HybridRAGEngine:
        engine = HybridRAGEngine()
        engine._initialized = True
        engine.dense_retriever = _EmptyRetriever()
        engine.sparse_retriever = _EmptyRetriever()
        engine.graph_retriever = _EmptyGraphRetriever()
        engine.fusion = _FakeFusion()
        engine.reranker = _FakeReranker()
        engine.generator = Mock(name="internal_generator")
        return engine

    async def test_external_route_uses_anonymized_prompt_and_deanonymized_answer(self) -> None:
        engine = self._build_engine()
        external_generator = Mock(name="external_generator")
        engine._get_external_generator = Mock(return_value=external_generator)
        engine._anonymize_prompt_variables = AsyncMock(
            return_value=(
                {
                    "context": "[PERSONA_1] guida il progetto.",
                    "query": "Chi e [PERSONA_1]?",
                },
                "session-1",
            )
        )
        engine._deanonymize_text = AsyncMock(return_value="Mario Rossi e il project manager.")
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="[PERSONA_1] e il project manager.",
                model="external-model",
                template_used="general_qa",
            )
        )

        with patch("app.rag.engine.settings.anonymizer_enabled", True), patch(
            "app.rag.engine.settings.external_llm_url",
            "https://llm.example.com/v1",
        ), patch("app.rag.engine.settings.external_llm_model", "gpt-test"):
            result = await engine.query(
                RAGQuery(text="Chi e Mario Rossi?", mode=QueryMode.QA)
            )

        self.assertEqual(result.answer, "Mario Rossi e il project manager.")
        self.assertEqual(result.llm_route, LLMRoute.EXTERNAL_ANONYMIZED)
        self.assertTrue(result.anonymized)
        self.assertEqual(result.sources[0]["metadata"]["document_id"], "doc-1")

        call_kwargs = engine._generate.await_args.kwargs
        self.assertIs(call_kwargs["generator"], external_generator)
        self.assertEqual(call_kwargs["variables"]["query"], "Chi e [PERSONA_1]?")
        engine._deanonymize_text.assert_awaited_once_with(
            "[PERSONA_1] e il project manager.",
            "session-1",
        )

    async def test_anonymizer_failure_falls_back_to_internal_llm(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock(
            side_effect=AnonymizerUnavailableError("down")
        )
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="Risposta interna di fallback.",
                model="internal-model",
                template_used="general_qa",
            )
        )

        with patch("app.rag.engine.settings.anonymizer_enabled", True), patch(
            "app.rag.engine.settings.external_llm_url",
            "https://llm.example.com/v1",
        ):
            result = await engine.query(RAGQuery(text="Domanda sensibile", mode=QueryMode.QA))

        self.assertEqual(result.answer, "Risposta interna di fallback.")
        self.assertEqual(result.llm_route, LLMRoute.INTERNAL_FALLBACK)
        self.assertFalse(result.anonymized)
        self.assertIs(engine._generate.await_args.kwargs["generator"], engine.generator)

    async def test_internal_route_skips_anonymizer_when_external_llm_is_not_configured(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock()
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="Risposta locale.",
                model="internal-model",
                template_used="general_qa",
            )
        )

        with patch("app.rag.engine.settings.anonymizer_enabled", True), patch(
            "app.rag.engine.settings.external_llm_url",
            "",
        ):
            result = await engine.query(RAGQuery(text="Domanda locale", mode=QueryMode.QA))

        self.assertEqual(result.answer, "Risposta locale.")
        self.assertEqual(result.llm_route, LLMRoute.INTERNAL)
        self.assertFalse(result.anonymized)
        engine._anonymize_prompt_variables.assert_not_awaited()

    async def test_anonymizer_circuit_open_short_circuits_requests(self) -> None:
        engine = self._build_engine()
        engine._anonymizer_circuit_open_until = 100.0

        with patch("app.rag.engine.time.monotonic", return_value=50.0), patch(
            "app.rag.engine.settings.anonymizer_url",
            "http://tw-anonymizer:8090",
        ):
            with self.assertRaises(AnonymizerUnavailableError):
                await engine._anonymize_chunks(["chunk sensibile"])

    def test_repeated_failures_open_anonymizer_circuit(self) -> None:
        engine = self._build_engine()

        with patch(
            "app.rag.engine.settings.anonymizer_circuit_breaker_threshold",
            2,
        ), patch(
            "app.rag.engine.settings.anonymizer_circuit_open_seconds",
            30.0,
        ), patch("app.rag.engine.time.monotonic", return_value=10.0):
            engine._record_anonymizer_failure(reason="timeout")
            engine._record_anonymizer_failure(reason="timeout")

        self.assertEqual(engine._anonymizer_failure_count, 2)
        self.assertEqual(engine._anonymizer_circuit_open_until, 40.0)


if __name__ == "__main__":
    unittest.main()
