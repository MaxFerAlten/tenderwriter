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

    async def _collect_stream(self, iterator) -> str:
        chunks: list[str] = []
        async for item in iterator:
            chunks.append(item)
        return "".join(chunks)

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
        trace = engine.get_last_privacy_debug_trace()
        self.assertIsNotNone(trace)
        self.assertEqual(trace["llm_route"], "external_anonymized")
        self.assertTrue(trace["anonymized"])
        self.assertEqual(
            trace["anonymized_prompt_variables"]["query"],
            "Chi e [PERSONA_1]?",
        )

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

    async def test_extension_failure_keeps_initial_answer(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock()
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="Risposta iniziale gia valida.",
                model="internal-model",
                template_used="general_qa",
            )
        )
        engine._extend_answer_if_needed = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch("app.rag.engine.settings.anonymizer_enabled", False), patch(
            "app.rag.engine.settings.external_llm_url",
            "",
        ):
            result = await engine.query(
                RAGQuery(
                    text="riassumimi il problema di assegnamento con 1000 parole",
                    mode=QueryMode.QA,
                )
            )

        self.assertEqual(result.answer, "Risposta iniziale gia valida.")
        self.assertEqual(result.llm_route, LLMRoute.INTERNAL)
        self.assertEqual(result.generation_result.text, "Risposta iniziale gia valida.")

    def test_long_word_requests_use_larger_completion_budget(self) -> None:
        engine = self._build_engine()

        self.assertEqual(engine._completion_token_budget_for_words(1000), 3072)
        self.assertEqual(engine._completion_token_budget_for_words(600), 2048)
        self.assertEqual(engine._completion_token_budget_for_words(200), 600)

    def test_line_requests_are_normalized_to_approximate_word_targets(self) -> None:
        engine = self._build_engine()

        target = engine._extract_requested_length_target(
            "parlami del problema di assegnamento 1000 righe"
        )

        self.assertIsNotNone(target)
        self.assertEqual(target.requested_unit, "lines")
        self.assertEqual(target.requested_value, 1000)
        self.assertEqual(target.target_words, 8000)
        self.assertTrue(target.approximate)
        self.assertEqual(
            engine._query_text_without_length_request(
                "parlami del problema di assegnamento 1000 righe"
            ),
            "parlami del problema di assegnamento",
        )

    def test_external_long_form_budget_is_not_capped_like_internal(self) -> None:
        engine = self._build_engine()
        length_target = engine._extract_requested_length_target(
            "parlami del problema di assegnamento 1000 righe"
        )

        external_generator = SimpleNamespace(provider="openrouter")
        internal_generator = SimpleNamespace(provider="llama")

        self.assertEqual(
            engine._generation_pass_token_budget(
                length_target,
                generator=external_generator,
            ),
            4096,
        )
        self.assertEqual(
            engine._generation_pass_token_budget(
                length_target,
                generator=internal_generator,
            ),
            512,
        )

    def test_detects_when_trailing_sentence_needs_completion(self) -> None:
        engine = self._build_engine()

        self.assertTrue(
            engine._needs_sentence_completion(
                "Il problema di assegnamento si collega anche al trasporto"
            )
        )
        self.assertFalse(
            engine._needs_sentence_completion(
                "Il problema di assegnamento si collega anche al trasporto."
            )
        )

    async def test_complete_trailing_sentence_if_needed_appends_short_closure(self) -> None:
        engine = self._build_engine()
        fake_generator = Mock(provider="openrouter")
        fake_generator.generate = AsyncMock(
            return_value=GenerationResult(
                text="ottimo in modo naturale e coerente.",
                model="qwen-test",
                template_used="custom",
                completion_tokens=18,
            )
        )

        completion = await engine._complete_trailing_sentence_if_needed(
            RAGQuery(text="spiega il problema di assegnamento", mode=QueryMode.QA),
            generator=fake_generator,
            context="contesto di test",
            variables={
                "query": "spiega il problema di assegnamento",
                "context": "contesto di test",
            },
            current_text="Il problema di assegnamento si collega anche al trasporto",
        )

        self.assertIsNotNone(completion)
        self.assertEqual(
            completion.text,
            "ottimo in modo naturale e coerente.",
        )
        fake_generator.generate.assert_awaited_once()

    def test_clean_continuation_text_stops_before_prompt_leakage_sections(self) -> None:
        engine = self._build_engine()

        cleaned = engine._sanitize_continuation_text(
            "Paragrafo iniziale.",
            "Nuovo paragrafo utile.\n\n## Draft Ending\nVecchio testo che non deve rientrare.",
        )

        self.assertEqual(cleaned, "Nuovo paragrafo utile.")

    def test_deduplicate_repeated_paragraphs_removes_looping_blocks(self) -> None:
        engine = self._build_engine()

        cleaned = engine._deduplicate_repeated_paragraphs(
            "Primo blocco.\n\nInoltre, il fornitore puo scegliere i prezzi f e g.\n\n"
            "Inoltre, il fornitore puo scegliere i prezzi f e g.\n\n"
            "Conclusione finale."
        )

        self.assertEqual(
            cleaned,
            "Primo blocco.\n\nInoltre, il fornitore puo scegliere i prezzi f e g.\n\nConclusione finale.",
        )

    def test_remove_length_meta_blocks_filters_word_count_chatter(self) -> None:
        engine = self._build_engine()

        cleaned = engine._remove_length_meta_blocks(
            "Spiegazione utile.\n\n"
            "parole sarebbero insufficienti per fornire una comprensione dettagliata del problema.\n\n"
            "Conclusione utile."
        )

        self.assertEqual(cleaned, "Spiegazione utile.\n\nConclusione utile.")

    def test_math_rendering_constraints_are_added_when_requested(self) -> None:
        engine = self._build_engine()

        constraints = engine._build_response_constraints(
            RAGQuery(
                text="spiega il problema di assegnamento e rendi ogni formula latex corretta",
                mode=QueryMode.QA,
            )
        )

        self.assertIn("notazione matematica leggibile e coerente", constraints)
        self.assertIn("pseudo-LaTeX incompleto", constraints)

    def test_local_generator_context_is_trimmed_to_budget(self) -> None:
        engine = self._build_engine()
        local_generator = SimpleNamespace(provider="llama")
        context = "\n\n---\n\n".join([
            "A" * 2500,
            "B" * 2500,
            "C" * 2500,
        ])

        fitted = engine._fit_context_for_generator(context, generator=local_generator)

        self.assertLessEqual(len(fitted), 4500)
        self.assertIn("A", fitted)

    def test_external_generator_keeps_full_context(self) -> None:
        engine = self._build_engine()
        external_generator = SimpleNamespace(provider="openrouter")
        context = "X" * 7000

        fitted = engine._fit_context_for_generator(context, generator=external_generator)

        self.assertEqual(fitted, context)

    async def test_external_target_override_uses_dynamic_generator_configuration(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock(
            return_value=({"context": "[PERSONA_1]", "query": "Chi e [PERSONA_1]?"}, "session-9")
        )
        engine._deanonymize_text = AsyncMock(return_value="Mario Rossi")
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="[PERSONA_1]",
                model="dynamic-external",
                template_used="general_qa",
            )
        )

        with patch("app.rag.engine.settings.anonymizer_enabled", True):
            result = await engine.query(
                RAGQuery(
                    text="Chi e Mario Rossi?",
                    mode=QueryMode.QA,
                    external_target_url="https://gateway.example.com/v1",
                    external_target_model="gpt-tender",
                    external_target_provider="openai",
                    external_target_timeout_ms=9000,
                    external_target_id=11,
                )
            )

        self.assertEqual(result.llm_route, LLMRoute.EXTERNAL_ANONYMIZED)
        generator_used = engine._generate.await_args.kwargs["generator"]
        self.assertEqual(generator_used.base_url, "https://gateway.example.com/v1")
        self.assertEqual(generator_used.model, "gpt-tender")

    async def test_query_stream_buffers_external_route_then_deanonymizes(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock(
            return_value=(
                {"context": "[PERSONA_1] guida il progetto.", "query": "Chi e [PERSONA_1]?"},
                "session-stream",
            )
        )
        engine._deanonymize_text = AsyncMock(return_value="Mario Rossi guida il progetto.")

        external_generator = Mock()

        async def fake_generate_stream(**_kwargs):
            for token in ("[PERSONA_1]", " guida", " il progetto."):
                yield token

        external_generator.generate_stream = fake_generate_stream
        engine._get_external_generator = Mock(return_value=external_generator)

        with patch("app.rag.engine.settings.anonymizer_enabled", True):
            output = await self._collect_stream(
                engine.query_stream(
                    RAGQuery(
                        text="Chi e Mario Rossi?",
                        mode=QueryMode.QA,
                        external_target_url="https://gateway.example.com/v1",
                        external_target_model="gpt-tender",
                    )
                )
            )

        self.assertEqual(output, "Mario Rossi guida il progetto.")
        engine._deanonymize_text.assert_awaited_once_with(
            "[PERSONA_1] guida il progetto.",
            "session-stream",
        )

    async def test_query_stream_passes_large_budget_to_external_generator_for_line_requests(self) -> None:
        engine = self._build_engine()
        captured_calls: list[dict] = []
        engine._continuation_attempt_budget = Mock(return_value=1)

        async def capture_anonymize(variables):
            captured_calls.append({"anonymized_query": variables["query"]})
            return variables, "session-lines"

        engine._anonymize_prompt_variables = AsyncMock(side_effect=capture_anonymize)
        engine._deanonymize_text = AsyncMock(side_effect=lambda text, _session: text)

        external_generator = Mock(provider="openrouter")

        async def fake_generate_stream(**kwargs):
            captured_calls.append(kwargs)
            yield "Risposta lunga."

        external_generator.generate_stream = fake_generate_stream
        engine._get_external_generator = Mock(return_value=external_generator)

        with patch("app.rag.engine.settings.anonymizer_enabled", True):
            output = await self._collect_stream(
                engine.query_stream(
                    RAGQuery(
                        text="parlami del problema di assegnamento 1000 righe",
                        mode=QueryMode.QA,
                        external_target_url="https://gateway.example.com/v1",
                        external_target_model="qwen-test",
                        external_target_provider="openrouter",
                    )
                )
            )

        self.assertEqual(output, "Risposta lunga.")
        self.assertEqual(
            captured_calls[0]["anonymized_query"],
            "parlami del problema di assegnamento",
        )
        self.assertEqual(captured_calls[1]["max_tokens"], 4096)

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
