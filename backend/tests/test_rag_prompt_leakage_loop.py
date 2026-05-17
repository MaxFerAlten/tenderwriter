"""Focused tests for prompt leakage loop cleanup."""

from __future__ import annotations

import os
import sys
import types
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


if "pydantic_settings" not in sys.modules:
    fake_pydantic_settings = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        def __init__(self, **kwargs):
            annotations: dict[str, object] = {}
            for cls in reversed(self.__class__.mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for field_name in annotations:
                env_name = field_name.upper()
                if field_name in kwargs:
                    value = kwargs[field_name]
                elif env_name in os.environ:
                    value = os.environ[env_name]
                else:
                    value = getattr(self.__class__, field_name, None)
                setattr(self, field_name, value)

    fake_pydantic_settings.BaseSettings = _BaseSettings
    sys.modules["pydantic_settings"] = fake_pydantic_settings

if "pydantic" not in sys.modules:
    fake_pydantic = types.ModuleType("pydantic")

    def _model_validator(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    def _field(*args, default=None, **kwargs):
        # app.config uses Field(default=..., validation_alias=...) for a
        # plain class attribute; the fake BaseSettings reads that default
        # via getattr(cls, name) and applies env overrides itself, so
        # returning the declared default is sufficient for the stub.
        del args, kwargs
        return default

    fake_pydantic.model_validator = _model_validator
    fake_pydantic.Field = _field
    sys.modules["pydantic"] = fake_pydantic

if "httpx" not in sys.modules:
    fake_httpx = types.ModuleType("httpx")

    class _HttpxError(Exception):
        pass

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

    fake_httpx.AsyncClient = _AsyncClient
    fake_httpx.Response = object
    fake_httpx.HTTPStatusError = _HttpxError
    fake_httpx.TimeoutException = _HttpxError
    fake_httpx.TransportError = _HttpxError
    sys.modules["httpx"] = fake_httpx

if "structlog" not in sys.modules:
    fake_structlog = types.ModuleType("structlog")

    class _FakeLogger:
        def info(self, *args, **kwargs):
            del args, kwargs

        def warning(self, *args, **kwargs):
            del args, kwargs

        def debug(self, *args, **kwargs):
            del args, kwargs

        def error(self, *args, **kwargs):
            del args, kwargs

    fake_structlog.get_logger = lambda *args, **kwargs: _FakeLogger()
    sys.modules["structlog"] = fake_structlog


fake_chunker = types.ModuleType("app.rag.chunker")


class _SemanticChunker:
    def __init__(self, *args, **kwargs):
        del args, kwargs


@dataclass
class _ChunkMetadata:
    document_id: int | None = None


@dataclass
class _TextChunk:
    text: str
    metadata: object


fake_chunker.SemanticChunker = _SemanticChunker
fake_chunker.ChunkMetadata = _ChunkMetadata
fake_chunker.TextChunk = _TextChunk
sys.modules.setdefault("app.rag.chunker", fake_chunker)

fake_dense = types.ModuleType("app.rag.dense_retriever")
fake_dense.DenseRetriever = type("DenseRetriever", (), {})
sys.modules.setdefault("app.rag.dense_retriever", fake_dense)

fake_embedder = types.ModuleType("app.rag.embedder")
fake_embedder.Embedder = type("Embedder", (), {})
fake_embedder.get_embedder = lambda: object()
sys.modules.setdefault("app.rag.embedder", fake_embedder)

fake_fusion = types.ModuleType("app.rag.fusion")
fake_fusion.RankFusion = type("RankFusion", (), {})
sys.modules.setdefault("app.rag.fusion", fake_fusion)

fake_generator = types.ModuleType("app.rag.generator")


@dataclass
class _GenerationResult:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    template_used: str = ""


class _Generator:
    provider = "llama"


fake_generator.GenerationResult = _GenerationResult
fake_generator.Generator = _Generator
sys.modules.setdefault("app.rag.generator", fake_generator)

fake_graph = types.ModuleType("app.rag.graph_retriever")
fake_graph.GraphRetriever = type("GraphRetriever", (), {})
sys.modules.setdefault("app.rag.graph_retriever", fake_graph)

fake_reranker = types.ModuleType("app.rag.reranker")
fake_reranker.Reranker = type("Reranker", (), {})
sys.modules.setdefault("app.rag.reranker", fake_reranker)

fake_sparse = types.ModuleType("app.rag.sparse_retriever")
fake_sparse.SparseRetriever = type("SparseRetriever", (), {})
sys.modules.setdefault("app.rag.sparse_retriever", fake_sparse)


from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery


class PromptLeakageLoopTests(unittest.TestCase):
    def _collect_stream(self, iterator):
        async def collect() -> str:
            chunks: list[str] = []
            async for chunk in iterator:
                chunks.append(chunk)
            return "".join(chunks)

        import asyncio

        return asyncio.run(collect())

    def test_structured_tender_overview_constraints_include_required_sections(self) -> None:
        engine = HybridRAGEngine()

        constraints = engine._build_response_constraints(
            RAGQuery(
                text="Prepara un elenco dettagliato della gara e dei punti critici",
                mode=QueryMode.QA,
            )
        )

        self.assertIn("Oggetto e perimetro", constraints)
        self.assertIn("Architettura tecnologica", constraints)
        self.assertIn("Fasi operative critiche", constraints)
        self.assertIn("Punti di rischio contrattuale", constraints)
        self.assertIn("Governance multi-soggetto", constraints)
        self.assertIn("non disponibile nei documenti forniti", constraints)
        self.assertIn("prosa narrativa coesa", constraints)

    def test_explicit_word_target_uses_timeout_safe_initial_token_budget_for_local_model(
        self,
    ) -> None:
        engine = HybridRAGEngine()
        length_target = engine._extract_requested_length_target("Riassumi la gara in 1000 parole")

        budget = engine._generation_pass_token_budget(
            length_target,
            generator=SimpleNamespace(provider="llama"),
        )

        self.assertEqual(budget, 1536)

    def test_guarded_tender_overview_buffers_streaming_even_with_word_target(self) -> None:
        engine = HybridRAGEngine()
        query = "descrivimi la gara della regione sardegna evidenzia i punti critici in 1000 parole"

        should_buffer = engine._should_buffer_stream_for_quality(
            RAGQuery(
                text=query,
                mode=QueryMode.QA,
            )
        )

        self.assertTrue(should_buffer)

    def test_guardrail_disabled_keeps_explicit_word_target_unbuffered(self) -> None:
        engine = HybridRAGEngine()
        query = "descrivimi la gara della regione sardegna evidenzia i punti critici in 1000 parole"

        should_buffer = engine._should_buffer_stream_for_quality(
            RAGQuery(
                text=query,
                mode=QueryMode.QA,
                guardrail_config={"enabled": False},
            )
        )

        self.assertFalse(should_buffer)

    def test_clean_final_answer_text_removes_repeated_own_answer_loop(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "Dettaglio utile sulla gara.\n"
            "own answer own answer own answer user question own answer own answer\n"
            "Conclusione utile."
        )

        self.assertEqual(cleaned, "Dettaglio utile sulla gara.\nConclusione utile.")

    def test_clean_final_answer_text_removes_inline_restarted_sections(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "**Dettagli della Gara e Ambito Operativo** La Regione Toscana ha indetto "
            "una procedura per il Sistema Cloud Toscano. In parallelo emerge una "
            "procedura specifica (Gara/."
            "**Dettagli della Gara e Ambito Operativo** La Regione Toscana ha indetto "
            "una procedura per il Sistema Cloud Toscano. In parallelo emerge una "
            "procedura specifica (Gara 012942/25) dedicata alla piattaforma OSCAT."
            " **Aspetti Tecnologici e Infrastrutturali** L'architettura si basa sul "
            "Sistema Cloud Toscano."
        )

        self.assertEqual(cleaned.count("**Dettagli della Gara e Ambito Operativo**"), 1)
        self.assertIn("Gara 012942/25", cleaned)
        self.assertNotIn("Gara/.", cleaned)
        self.assertIn("\n\n**Aspetti Tecnologici e Infrastrutturali**", cleaned)

    def test_clean_final_answer_text_removes_common_generation_artifacts(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "Il consolidamento e sviluppo evolutivoを del Sistema Cloud Toscana. "
            "Un ulter ulteriore focus riguarda la Manutenzione Adeguativa e Migliore "
            "(MAM) presso il Settore Sistema Cloud Toscano, Infrastruttura Digitali "
            "e Piattaforme Abilitanti."
        )

        self.assertNotIn("を", cleaned)
        self.assertNotIn("ulter ulteriore", cleaned)
        self.assertNotIn("Migliore (MAM)", cleaned)
        self.assertNotIn("Infrastruttura Digitali", cleaned)

    def test_clean_final_answer_text_removes_generated_fact_sheet_prefix(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "Fatti verificati\n"
            "procedura: SCT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: non_rilevato\n"
            "giorni_critici: 180 giorni, 270 giorno\n"
            "durata: non_rilevato\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1200, chunk:943\n"
            "conflitti: nessuno\n\n"
            "La procedura SCT riguarda il Sistema Cloud Toscana."
        )

        self.assertEqual(
            cleaned,
            "La procedura SCT riguarda il Sistema Cloud Toscana.",
        )

    def test_clean_final_answer_text_generic_cig_cleanup(self) -> None:
        # Decontamination: the tender-specific OCR rule that force-rewrote
        # any B33988ECF* token to "CIG B33988ECF2" was removed. The generic
        # cleanup path must still repair generic OCR artifacts, but must NOT
        # apply the removed tender-specific CIG normalization.
        engine = HybridRAGEngine()

        # Generic, retained cleanup still works (OCR replacements +
        # plural-day repair from engine-cleanup-patterns.md).
        cleaned_generic = engine._clean_final_answer_text(
            "Un ulter ulteriore focus sulla Manutenzione Migliore (MAM) "
            "presso Infrastruttura Digitali, con termine entro 180 giorni, "
            "270 giorno."
        )
        self.assertNotIn("ulter ulteriore", cleaned_generic)
        self.assertIn("ulteriore", cleaned_generic)
        self.assertNotIn("Migliore (MAM)", cleaned_generic)
        self.assertIn("Migliorativa (MAM)", cleaned_generic)
        self.assertNotIn("Infrastruttura Digitali", cleaned_generic)
        self.assertIn("Infrastrutture Digitali", cleaned_generic)
        self.assertNotIn("270 giorno.", cleaned_generic)
        self.assertIn("270 giorni", cleaned_generic)

        # The removed tender-specific normalization must NOT be applied:
        # previously-mangled B33988ECF* tokens are left exactly as-is and
        # are NOT force-rewritten to "CIG B33988ECF2".
        cleaned_cig = engine._clean_final_answer_text(
            "Il capitolato indica il CIG B33988ECF1. "
            "In un altro passaggio il CIG B33988ECF3 viene richiamato in forma errata. "
            "La sintesi finale cita anche CIG B33988ECF."
        )
        self.assertEqual(cleaned_cig.count("CIG B33988ECF2"), 0)
        self.assertIn("CIG B33988ECF1", cleaned_cig)
        self.assertIn("CIG B33988ECF3", cleaned_cig)
        self.assertIn("CIG B33988ECF.", cleaned_cig)

        # A well-formed generic CIG is preserved intact (no spurious
        # rewrite by the generic cleanup path).
        cleaned_ok = engine._clean_final_answer_text(
            "Il bando riporta il CIG 9A1B2C3D4E come riferimento."
        )
        self.assertIn("CIG 9A1B2C3D4E", cleaned_ok)

    def test_structured_tender_overview_stream_uses_clean_full_answer(self) -> None:
        engine = HybridRAGEngine()
        engine.query = AsyncMock(
            return_value=SimpleNamespace(
                answer="**Dettagli della gara e ambito operativo** Testo pulito.",
            )
        )

        streamed = self._collect_stream(
            engine.query_stream(
                RAGQuery(
                    text="Prepara un elenco dettagliato della gara e dei punti critici",
                    mode=QueryMode.QA,
                )
            )
        )

        self.assertEqual(
            streamed,
            "**Dettagli della gara e ambito operativo** Testo pulito.",
        )
        engine.query.assert_awaited_once()

    def test_broad_tender_summary_stream_uses_clean_full_answer(self) -> None:
        engine = HybridRAGEngine()
        engine.query = AsyncMock(return_value=SimpleNamespace(answer="Sintesi pulita della gara."))

        streamed = self._collect_stream(
            engine.query_stream(
                RAGQuery(
                    text="Riassumi la gara Toscana",
                    mode=QueryMode.QA,
                )
            )
        )

        self.assertEqual(streamed, "Sintesi pulita della gara.")
        engine.query.assert_awaited_once()

    def test_clean_final_answer_text_removes_inline_own_answer_suffix(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "Dettaglio utile sulla gara s own answer own answer own answer "
            "user question own answer own answer"
        )

        self.assertEqual(cleaned, "Dettaglio utile sulla gara.")

    def test_clean_final_answer_text_removes_repeated_own_prefix_and_trailing_braces(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "s own own own own own own\n"
            "s own own own own own own L'analisi della gara della Regione Toscana.\n"
            "Dettaglio finale proporzionalmente}\n"
            "}\n"
            "}\n"
        )

        self.assertEqual(
            cleaned,
            "L'analisi della gara della Regione Toscana.\nDettaglio finale proporzionalmente.",
        )

    def test_clean_final_answer_text_removes_same_language_garbage_prefix(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "s own language:// a own own own own own own "
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali."
        )

        self.assertEqual(
            cleaned,
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali.",
        )

    def test_sanitize_continuation_text_removes_same_language_garbage_prefix(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._sanitize_continuation_text(
            "",
            "s own language:// a own own own own own own "
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali.",
        )

        self.assertEqual(
            cleaned,
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali.",
        )

    def test_clean_final_answer_text_preserves_accented_answer_start_after_garbage_prefix(
        self,
    ) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "s own language:// a own own own own own own "
            "è prevista una cauzione definitiva a carico dell'aggiudicatario."
        )

        self.assertEqual(
            cleaned,
            "è prevista una cauzione definitiva a carico dell'aggiudicatario.",
        )

    def test_clean_final_answer_text_drops_same_language_garbage_without_answer(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "s own language:// a own own own own own own "
            "fai dei test prima di concludere che va bene"
        )

        self.assertEqual(cleaned, "")


if __name__ == "__main__":
    unittest.main()
