"""Focused tests for detailed tender overview routing and generation budgets."""

from __future__ import annotations

import os
import sys
import types
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

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


from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery


class TenderOverviewLongFormTests(unittest.TestCase):
    def test_analyze_all_details_query_is_treated_as_detailed_tender_overview(self) -> None:
        engine = HybridRAGEngine()
        query = "analizza tutti i dettagli della gara toscana"

        self.assertTrue(engine._query_requests_broad_summary(query))
        self.assertTrue(engine._query_requests_structured_tender_overview(query))
        self.assertEqual(
            engine._effective_final_top_k(RAGQuery(text=query, mode=QueryMode.QA, top_k=5)), 12
        )
        self.assertEqual(
            engine._effective_retrieval_top_k(RAGQuery(text=query, mode=QueryMode.QA)), 30
        )
        self.assertEqual(engine._query_text_for_retrieval(query), "gara toscana")

    def test_detailed_tender_overview_gets_expanded_default_generation_budget(self) -> None:
        engine = HybridRAGEngine()
        max_tokens = engine._default_generation_pass_token_budget(
            RAGQuery(
                text="analizza tutti i dettagli della gara toscana",
                mode=QueryMode.QA,
            ),
            generator=SimpleNamespace(provider="llama"),
        )

        self.assertEqual(max_tokens, 1024)


if __name__ == "__main__":
    unittest.main()
