"""Focused tests for prompt leakage loop cleanup."""

from __future__ import annotations

import os
import sys
import types
import unittest
from dataclasses import dataclass

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

    fake_pydantic.model_validator = _model_validator
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


from app.rag.engine import HybridRAGEngine


class PromptLeakageLoopTests(unittest.TestCase):
    def test_clean_final_answer_text_removes_repeated_own_answer_loop(self) -> None:
        engine = HybridRAGEngine()

        cleaned = engine._clean_final_answer_text(
            "Dettaglio utile sulla gara.\n"
            "own answer own answer own answer user question own answer own answer\n"
            "Conclusione utile."
        )

        self.assertEqual(cleaned, "Dettaglio utile sulla gara.\nConclusione utile.")

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
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali."
        )

        self.assertEqual(
            cleaned,
            "L'analisi della gara della Regione Toscana e dei suoi requisiti principali.",
        )

    def test_clean_final_answer_text_preserves_accented_answer_start_after_garbage_prefix(self) -> None:
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
