import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

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

_fake_qdrant_client = ModuleType("qdrant_client")
_fake_qdrant_client.QdrantClient = object
_fake_qdrant_client.models = SimpleNamespace()

_fake_neo4j = ModuleType("neo4j")


class _FakeAsyncGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        return None


_fake_neo4j.AsyncGraphDatabase = _FakeAsyncGraphDatabase

_fake_rank_bm25 = ModuleType("rank_bm25")


class _FakeBM25Okapi:
    def __init__(self, corpus):
        self.corpus = corpus

    def get_scores(self, query_tokens):
        del query_tokens
        return [0.0 for _ in self.corpus]


_fake_rank_bm25.BM25Okapi = _FakeBM25Okapi

sys.modules.setdefault("qdrant_client", _fake_qdrant_client)
sys.modules.setdefault("neo4j", _fake_neo4j)
sys.modules.setdefault("rank_bm25", _fake_rank_bm25)

from app.rag.engine import (
    AnonymizerUnavailableError,
    HybridRAGEngine,
    LLMRoute,
    QueryMode,
    RAGQuery,
)
from app.rag.generator import PROMPT_TEMPLATES, GenerationResult


class _EmptyRetriever:
    def search(self, **_kwargs):
        return [
            SimpleNamespace(
                text="Mario Rossi guida il progetto.",
                score=0.91,
                metadata={"document_id": "doc-1"},
            )
        ]


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

        with (
            patch("app.rag.engine.settings.anonymizer_enabled", True),
            patch(
                "app.rag.engine.settings.external_llm_url",
                "https://llm.example.com/v1",
            ),
            patch("app.rag.engine.settings.external_llm_model", "gpt-test"),
        ):
            result = await engine.query(RAGQuery(text="Chi e Mario Rossi?", mode=QueryMode.QA))

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

        with (
            patch("app.rag.engine.settings.anonymizer_enabled", True),
            patch(
                "app.rag.engine.settings.external_llm_url",
                "https://llm.example.com/v1",
            ),
        ):
            result = await engine.query(RAGQuery(text="Domanda sensibile", mode=QueryMode.QA))

        self.assertEqual(result.answer, "Risposta interna di fallback.")
        self.assertEqual(result.llm_route, LLMRoute.INTERNAL_FALLBACK)
        self.assertFalse(result.anonymized)
        self.assertIs(engine._generate.await_args.kwargs["generator"], engine.generator)

    async def test_internal_route_skips_anonymizer_when_external_llm_is_not_configured(
        self,
    ) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock()
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="Risposta locale.",
                model="internal-model",
                template_used="general_qa",
            )
        )

        with (
            patch("app.rag.engine.settings.anonymizer_enabled", True),
            patch(
                "app.rag.engine.settings.external_llm_url",
                "",
            ),
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

        with (
            patch("app.rag.engine.settings.anonymizer_enabled", False),
            patch(
                "app.rag.engine.settings.external_llm_url",
                "",
            ),
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

    def test_long_word_requests_use_proportional_completion_budget(self) -> None:
        engine = self._build_engine()

        self.assertEqual(engine._completion_token_budget_for_words(1000), 3000)
        self.assertEqual(engine._completion_token_budget_for_words(600), 1800)
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
            1536,
        )
        self.assertEqual(
            engine._generation_pass_token_budget(
                length_target,
                generator=internal_generator,
                current_words=200,
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
        self.assertTrue(
            engine._needs_sentence_completion(
                "Il problema di assegnamento puo essere visto come un."
            )
        )

    def test_merge_sentence_completion_suffix_removes_suspicious_terminal_punctuation(self) -> None:
        engine = self._build_engine()

        merged = engine._merge_sentence_completion_suffix(
            "Il problema di assegnamento puo essere visto come un.",
            "caso particolare del trasporto ottimo.",
        )

        self.assertEqual(
            merged,
            "Il problema di assegnamento puo essere visto come un caso particolare del trasporto ottimo.",
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

    def test_clean_final_answer_text_removes_inline_answer_prompt_leakage_and_keeps_following_text(
        self,
    ) -> None:
        engine = self._build_engine()

        cleaned = engine._clean_final_answer_text(
            "Il problema di assegnamento e un problema classico. ## Answer (in the same language as the question)\n"
            "Approfondimento utile."
        )

        self.assertEqual(
            cleaned,
            "Il problema di assegnamento e un problema classico.\nApprofondimento utile.",
        )

    def test_clean_final_answer_text_removes_compito_prompt_leakage_and_keeps_following_text(
        self,
    ) -> None:
        engine = self._build_engine()

        cleaned = engine._clean_final_answer_text(
            "Il problema di assegnamento e un problema classico.\nCOMPITO:\n"
            "Continua solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto. Inizia direttamente con il testo mancante.\n"
            "Approfondimento finale."
        )

        self.assertEqual(
            cleaned,
            "Il problema di assegnamento e un problema classico.\nApprofondimento finale.",
        )

    def test_remove_length_meta_blocks_filters_word_count_chatter(self) -> None:
        engine = self._build_engine()

        cleaned = engine._remove_length_meta_blocks(
            "Spiegazione utile.\n\n"
            "parole sarebbero insufficienti per fornire una comprensione dettagliata del problema.\n\n"
            "Conclusione utile."
        )

        self.assertEqual(cleaned, "Spiegazione utile.\n\nConclusione utile.")

    def test_summary_queries_get_fuller_default_response_constraints(self) -> None:
        engine = self._build_engine()

        constraints = engine._build_response_constraints(
            RAGQuery(
                text="riassumimi il problema di assegnamento",
                mode=QueryMode.QA,
            )
        )

        self.assertIn("sviluppa una risposta un po' piu completa del minimo", constraints)

    def test_broad_tender_summary_queries_boost_effective_final_top_k(self) -> None:
        engine = self._build_engine()

        top_k = engine._effective_final_top_k(
            RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.QA,
                top_k=5,
            )
        )

        self.assertEqual(top_k, 10)

    def test_detailed_tender_overview_queries_boost_effective_final_top_k_more_aggressively(
        self,
    ) -> None:
        engine = self._build_engine()

        top_k = engine._effective_final_top_k(
            RAGQuery(
                text="fai un elenco dettagliato della gara toscana",
                mode=QueryMode.QA,
                top_k=5,
            )
        )

        self.assertEqual(top_k, 12)

    def test_detailed_tender_overview_queries_boost_retrieval_top_k(self) -> None:
        engine = self._build_engine()

        retrieval_top_k = engine._effective_retrieval_top_k(
            RAGQuery(
                text="fai un elenco dettagliato della gara toscana",
                mode=QueryMode.QA,
            )
        )

        self.assertEqual(retrieval_top_k, 30)

    def test_broad_tender_overview_queries_strip_instruction_words_from_retrieval_query(
        self,
    ) -> None:
        engine = self._build_engine()

        retrieval_query = engine._query_text_for_retrieval(
            "fai un elenco dettagliato della gara toscana"
        )

        self.assertEqual(retrieval_query, "gara toscana")

    def test_broad_tender_summary_constraints_prefer_best_effort_synthesis(self) -> None:
        engine = self._build_engine()

        constraints = engine._build_response_constraints(
            RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.QA,
            )
        )

        self.assertIn("migliore sintesi possibile", constraints)
        self.assertIn("aspetti non coperti", constraints)

    def test_detailed_tender_overview_constraints_require_sections_and_ocr_cleanup(self) -> None:
        engine = self._build_engine()

        constraints = engine._build_response_constraints(
            RAGQuery(
                text="fai un elenco dettagliato della gara toscana",
                mode=QueryMode.QA,
            )
        )

        self.assertIn("Oggetto e perimetro", constraints)
        self.assertIn("Fasi operative critiche", constraints)
        self.assertIn("Governance multi-soggetto", constraints)
        self.assertIn("frammenti OCR", constraints)

    def test_general_qa_prompt_keeps_grounding_and_best_effort_rules(self) -> None:
        template = PROMPT_TEMPLATES["general_qa"]

        self.assertIn("Use ONLY the retrieved context", template)
        self.assertIn("partial but relevant", template)
        self.assertIn("Output ONLY the answer text", template)

    def test_tender_overview_prompt_is_fact_sheet_first(self) -> None:
        template = PROMPT_TEMPLATES["tender_overview"]

        # Contract heading + the two ordered sections the model must
        # emit in this exact order.
        self.assertIn("FACT-SHEET-FIRST CONTRACT", template)
        self.assertIn('"Fatti verificati"', template)
        self.assertIn('"Analisi"', template)
        self.assertLess(
            template.index('"Fatti verificati"'),
            template.index('"Analisi"'),
            "Fatti verificati must precede Analisi in the contract",
        )

        # Fact-sheet-only sourcing: never invent protected values.
        self.assertIn(
            "Non usare numeri, CIG, importi, indirizzi, soggetti o procedure_id assenti dalla fact sheet",
            template,
        )

        # Conflict: keep useful analysis, but never emit conflicted protected values.
        self.assertIn(
            'Per ogni campo "conflitto_rilevato"',
            template,
        )
        self.assertIn(
            "riportare valori conflittuali",
            template,
        )
        self.assertIn(
            "continua comunque con l'analisi",
            template,
        )

        # non_rilevato handling.
        self.assertIn(
            'Per ogni campo "non_rilevato" nella fact sheet scrivi esattamente "non rilevato"',
            template,
        )

        # No repeated sections / restarted paragraphs.
        self.assertIn(
            "Non ripetere intestazioni, paragrafi o introduzioni",
            template,
        )
        self.assertIn(
            'Non ricominciare le sezioni "Fatti verificati" o "Analisi"',
            template,
        )

        # Bullet form for every protected field — guarantees the
        # answer-side leakage scrubber (which strips bare "field:"
        # lines) does NOT eat the legitimate verified-facts block.
        for label in (
            "Procedura:",
            "ID procedura:",
            "CIG:",
            "Giorni critici:",
            "Durata:",
            "Importi:",
            "Sedi/luoghi:",
            "Percentuali:",
        ):
            self.assertIn(f"- {label}", template)

    def test_tender_overview_prompt_does_not_drop_fact_sheet_envelope(self) -> None:
        # The retrieval-to-context wiring still ships FACT_SHEET_START /
        # SOURCE_START / SOURCE_END in the *context*; the contract must
        # reference those envelopes so the model knows where to look.
        template = PROMPT_TEMPLATES["tender_overview"]
        self.assertIn("FACT_SHEET_START", template)
        self.assertIn("FACT_SHEET_END", template)
        self.assertIn("SOURCE_START", template)
        self.assertIn("SOURCE_END", template)

    def test_search_mode_resolve_template_includes_response_constraints(self) -> None:
        engine = self._build_engine()

        template_name, variables = engine._resolve_template(
            RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.SEARCH,
            ),
            context="Contesto sintetico",
        )

        self.assertEqual(template_name, "general_qa")
        self.assertEqual(variables["context"], "Contesto sintetico")
        self.assertIn("response_constraints", variables)
        self.assertTrue(variables["response_constraints"].strip())

    def test_resolve_retriever_selection_falls_back_to_defaults_when_everything_is_disabled(
        self,
    ) -> None:
        engine = self._build_engine()

        selection = engine._resolve_retriever_selection(
            RAGQuery(
                text="assignment",
                mode=QueryMode.QA,
                retrievers={"dense": False, "sparse": False, "graph": False},
            )
        )

        self.assertEqual(selection, {"dense": True, "sparse": True, "graph": True})

    def test_resolve_fusion_weights_clamps_invalid_values(self) -> None:
        engine = self._build_engine()

        weights = engine._resolve_fusion_weights(
            RAGQuery(
                text="assignment",
                mode=QueryMode.QA,
                fusion_weights={"dense": 5, "sparse": 0, "graph": 0.75},
            )
        )

        self.assertEqual(weights, {"dense": 2.0, "sparse": 0.05, "graph": 0.75})

    async def test_retrieve_context_and_sources_skips_disabled_retrievers(self) -> None:
        engine = self._build_engine()
        engine.dense_retriever = Mock(
            search=Mock(
                return_value=[
                    SimpleNamespace(
                        text="Risultato dense",
                        score=0.9,
                        metadata={"source": "dense"},
                    )
                ]
            )
        )
        engine.sparse_retriever = Mock(search=Mock(return_value=[]))
        engine.graph_retriever = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        text="Risultato graph",
                        score=0.8,
                        metadata={"source": "graph"},
                    )
                ]
            )
        )
        engine.reranker = SimpleNamespace(
            rerank=Mock(
                return_value=[
                    {
                        "text": "Risultato dense",
                        "score": 0.9,
                        "metadata": {"source": "dense"},
                    }
                ]
            )
        )

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="assignment",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": True},
            )
        )

        engine.dense_retriever.search.assert_called_once()
        engine.sparse_retriever.search.assert_not_called()
        engine.graph_retriever.search.assert_awaited_once()
        self.assertIn("Risultato dense", retrieved.context)

    async def test_retrieve_context_and_sources_uses_more_final_chunks_for_broad_tender_summary(
        self,
    ) -> None:
        engine = self._build_engine()
        distinct_terms = [
            "alpha bravo charlie delta echo foxtrot",
            "hotel india juliet kilo lima mike",
            "november oscar papa quebec romeo sierra",
            "tango uniform victor whiskey xray yankee",
            "red green blue yellow cyan magenta",
            "north south east west central island",
            "storage network compute backup archive",
            "monitor audit report ledger control",
            "ticket workflow approval calendar notice",
            "privacy security identity access policy",
            "migration rollout training support service",
            "testing quality release incident change",
        ]
        engine.dense_retriever = Mock(
            search=Mock(
                return_value=[
                    SimpleNamespace(
                        text=(
                            f"{distinct_terms[idx]} area funzionale {idx} con contenuto "
                            "specifico per la sintesi del bando."
                        ),
                        score=1.0 - idx * 0.01,
                        metadata={"source": f"dense-{idx}"},
                    )
                    for idx in range(12)
                ]
            )
        )
        engine.sparse_retriever = Mock(search=Mock(return_value=[]))
        engine.graph_retriever = SimpleNamespace(search=AsyncMock(return_value=[]))
        rerank_calls: list[dict] = []

        def fake_rerank(**kwargs):
            rerank_calls.append(kwargs)
            return kwargs["results"][: kwargs["top_k"]]

        engine.reranker = SimpleNamespace(rerank=Mock(side_effect=fake_rerank))

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.QA,
                top_k=5,
            )
        )

        self.assertGreaterEqual(rerank_calls[0]["top_k"], 10)
        self.assertEqual(len(retrieved.sources), 10)

    async def test_broad_tender_summary_backfills_after_context_deduplication(self) -> None:
        engine = self._build_engine()
        duplicated = [
            (f"SCT CCTT gestione servizi cloud qualificazione ACN entro 210 giorni variante {idx}.")
            for idx in range(10)
        ]
        distinct_terms = [
            "alpha bravo charlie delta echo foxtrot",
            "hotel india juliet kilo lima mike",
            "november oscar papa quebec romeo sierra",
            "tango uniform victor whiskey xray yankee",
            "red green blue yellow cyan magenta",
            "north south east west central island",
            "storage network compute backup archive",
            "monitor audit report ledger control",
            "ticket workflow approval calendar notice",
            "privacy security identity access policy",
        ]
        unique_tail = [
            f"{distinct_terms[idx]} SCT area unica {idx} con oggetto e perimetro distintivi."
            for idx in range(10)
        ]
        engine.dense_retriever = Mock(
            search=Mock(
                return_value=[
                    SimpleNamespace(
                        text=text,
                        score=1.0 - idx * 0.01,
                        metadata={"source": f"dense-{idx}", "chunk_index": idx},
                    )
                    for idx, text in enumerate(duplicated + unique_tail)
                ]
            )
        )
        engine.sparse_retriever = Mock(search=Mock(return_value=[]))
        engine.graph_retriever = SimpleNamespace(search=AsyncMock(return_value=[]))
        engine.reranker = SimpleNamespace(
            rerank=Mock(side_effect=lambda **kwargs: kwargs["results"][: kwargs["top_k"]])
        )

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.QA,
                top_k=5,
            )
        )

        self.assertEqual(len(retrieved.sources), 10)
        self.assertTrue(
            any("area unica" in str(source.get("text", "")) for source in retrieved.sources)
        )

    async def test_retrieve_context_and_sources_uses_more_chunks_for_detailed_tender_overview(
        self,
    ) -> None:
        engine = self._build_engine()
        distinct_terms = [
            "alpha bravo charlie delta echo foxtrot",
            "hotel india juliet kilo lima mike",
            "november oscar papa quebec romeo sierra",
            "tango uniform victor whiskey xray yankee",
            "red green blue yellow cyan magenta",
            "north south east west central island",
            "storage network compute backup archive",
            "monitor audit report ledger control",
            "ticket workflow approval calendar notice",
            "privacy security identity access policy",
            "migration rollout training support service",
            "testing quality release incident change",
            "database queue cache index shard replica",
            "contract annex schedule penalty threshold",
            "supplier operator manager director committee",
            "cloud platform registry pipeline scanner",
        ]
        engine.dense_retriever = Mock(
            search=Mock(
                return_value=[
                    SimpleNamespace(
                        text=(
                            f"{distinct_terms[idx]} sezione tecnica {idx} con elementi "
                            "distintivi per elenco dettagliato della gara."
                        ),
                        score=1.0 - idx * 0.01,
                        metadata={"source": f"dense-{idx}"},
                    )
                    for idx in range(16)
                ]
            )
        )
        engine.sparse_retriever = Mock(search=Mock(return_value=[]))
        engine.graph_retriever = SimpleNamespace(search=AsyncMock(return_value=[]))
        rerank_calls: list[dict] = []

        def fake_rerank(**kwargs):
            rerank_calls.append(kwargs)
            return kwargs["results"][: kwargs["top_k"]]

        engine.reranker = SimpleNamespace(rerank=Mock(side_effect=fake_rerank))

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="fai un elenco dettagliato della gara toscana",
                mode=QueryMode.QA,
                top_k=5,
            )
        )

        self.assertIn(
            call(query="gara toscana", top_k=30, filters=None),
            engine.dense_retriever.search.call_args_list,
        )
        self.assertGreaterEqual(engine.dense_retriever.search.call_count, 1)
        self.assertGreaterEqual(rerank_calls[0]["top_k"], 12)
        self.assertEqual(len(retrieved.sources), 12)

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
        context = "\n\n---\n\n".join(
            [
                "A" * 2500,
                "B" * 2500,
                "C" * 2500,
            ]
        )

        fitted = engine._fit_context_for_generator(context, generator=local_generator)

        self.assertLessEqual(len(fitted), 4500)
        self.assertIn("A", fitted)

    def test_external_generator_keeps_full_context(self) -> None:
        engine = self._build_engine()
        external_generator = SimpleNamespace(provider="openrouter")
        context = "X" * 7000

        fitted = engine._fit_context_for_generator(context, generator=external_generator)

        self.assertEqual(fitted, context)

    def test_broad_tender_summary_local_generator_gets_expanded_context_budget(self) -> None:
        engine = self._build_engine()
        local_generator = SimpleNamespace(provider="llama")
        context = "\n\n---\n\n".join(
            [
                "A" * 3800,
                "B" * 3800,
                "C" * 3800,
                "D" * 3800,
            ]
        )

        fitted = engine._fit_context_for_generator(
            context,
            generator=local_generator,
            rag_query=RAGQuery(
                text="riassumi il bando della regione toscana",
                mode=QueryMode.QA,
            ),
        )

        self.assertLessEqual(len(fitted), 12000)
        self.assertGreater(len(fitted), 4500)
        self.assertIn("A", fitted)
        self.assertIn("B", fitted)

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

    async def test_query_stream_deanonymizes_external_route_incrementally(self) -> None:
        engine = self._build_engine()
        engine._anonymize_prompt_variables = AsyncMock(
            return_value=(
                {
                    "context": "[PERSONA_1] coordina il progetto.",
                    "query": "Descrivi il ruolo di [PERSONA_1].",
                },
                "session-stream",
            )
        )
        engine._deanonymize_text = AsyncMock(
            side_effect=lambda text, _session: text.replace("[PERSONA_1]", "Mario Rossi")
        )

        external_generator = Mock()

        async def fake_generate_stream(**_kwargs):
            for token in (
                "[PERSONA_1] coordina il progetto e definisce le milestone principali. ",
                "Gestisce il team operativo e valida i deliverable conclusivi.",
            ):
                yield token

        external_generator.generate_stream = fake_generate_stream
        engine._get_external_generator = Mock(return_value=external_generator)

        chunks: list[str] = []
        with patch("app.rag.engine.settings.anonymizer_enabled", True):
            async for item in engine.query_stream(
                RAGQuery(
                    text="Descrivi il ruolo di Mario Rossi.",
                    mode=QueryMode.QA,
                    external_target_url="https://gateway.example.com/v1",
                    external_target_model="gpt-tender",
                )
            ):
                chunks.append(item)

        self.assertEqual(
            "".join(chunks),
            "Mario Rossi coordina il progetto e definisce le milestone principali. Gestisce il team operativo e valida i deliverable conclusivi.",
        )
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all("[PERSONA_1]" not in chunk for chunk in chunks))
        self.assertGreaterEqual(engine._deanonymize_text.await_count, 1)
        self.assertTrue(
            all(
                await_call.args[1] == "session-stream"
                for await_call in engine._deanonymize_text.await_args_list
            )
        )
        self.assertTrue(
            any(
                "[PERSONA_1]" in await_call.args[0]
                for await_call in engine._deanonymize_text.await_args_list
            )
        )

    async def test_query_stream_passes_large_budget_to_external_generator_for_line_requests(
        self,
    ) -> None:
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

    async def test_query_stream_does_not_inject_blank_block_between_attempts(self) -> None:
        engine = self._build_engine()
        engine._continuation_attempt_budget = Mock(return_value=2)
        engine._complete_trailing_sentence_if_needed = AsyncMock(return_value=None)
        engine._anonymize_prompt_variables = AsyncMock(
            return_value=(
                {
                    "context": "[PERSONA_1] coordina il progetto.",
                    "query": "Descrivi il ruolo di [PERSONA_1].",
                },
                "session-multipass",
            )
        )
        engine._deanonymize_text = AsyncMock(
            side_effect=lambda text, _session: text.replace("[PERSONA_1]", "Mario Rossi")
        )

        external_generator = Mock(provider="openrouter")
        call_count = 0

        async def fake_generate_stream(**_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield "[PERSONA_1] coordina il progetto."
            else:
                yield "Gestisce il team operativo."

        external_generator.generate_stream = fake_generate_stream
        engine._get_external_generator = Mock(return_value=external_generator)

        with patch("app.rag.engine.settings.anonymizer_enabled", True):
            output = await self._collect_stream(
                engine.query_stream(
                    RAGQuery(
                        text="Descrivi il ruolo di Mario Rossi in 1000 righe",
                        mode=QueryMode.QA,
                        external_target_url="https://gateway.example.com/v1",
                        external_target_model="gpt-tender",
                        external_target_provider="openrouter",
                    )
                )
            )

        self.assertEqual(
            output,
            "Mario Rossi coordina il progetto. Gestisce il team operativo.",
        )
        self.assertNotIn("\n\n", output)

    async def test_anonymizer_circuit_open_short_circuits_requests(self) -> None:
        engine = self._build_engine()
        engine._anonymizer_circuit_open_until = 100.0

        with (
            patch("app.rag.engine.time.monotonic", return_value=50.0),
            patch(
                "app.rag.engine.settings.anonymizer_url",
                "http://tw-anonymizer:8090",
            ),
        ):
            with self.assertRaises(AnonymizerUnavailableError):
                await engine._anonymize_chunks(["chunk sensibile"])

    def test_repeated_failures_open_anonymizer_circuit(self) -> None:
        engine = self._build_engine()

        with (
            patch(
                "app.rag.engine.settings.anonymizer_circuit_breaker_threshold",
                2,
            ),
            patch(
                "app.rag.engine.settings.anonymizer_circuit_open_seconds",
                30.0,
            ),
            patch("app.rag.engine.time.monotonic", return_value=10.0),
        ):
            engine._record_anonymizer_failure(reason="timeout")
            engine._record_anonymizer_failure(reason="timeout")

        self.assertEqual(engine._anonymizer_failure_count, 2)
        self.assertEqual(engine._anonymizer_circuit_open_until, 40.0)


if __name__ == "__main__":
    unittest.main()
