"""Targeted diagnostic and regression tests for high-risk defects.

These tests stay narrow on purpose: they reproduce the defect or protect the
fix without requiring the full production dependency graph in the test
environment.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from textwrap import dedent
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from jinja2 import Environment, select_autoescape
from sqlalchemy.dialects import postgresql

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


class _CreateOnlyDb:
    """Small fake DB for anonymous content-library write diagnostics."""

    def __init__(self) -> None:
        self.row = None
        self.add = Mock(side_effect=self._add)
        self.flush = AsyncMock()
        self.refresh = AsyncMock(side_effect=self._refresh)

    def _add(self, row) -> None:
        self.row = row

    async def _refresh(self, row) -> None:
        if getattr(row, "id", None) is None:
            row.id = 1


class _ExecuteResult:
    """Small SQLAlchemy-like result wrapper for list diagnostics."""

    def __init__(self, *, scalar_value=None, rows=None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ListCaptureDb:
    """Capture generated statements from list/search endpoints."""

    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _ExecuteResult(scalar_value=0)
        return _ExecuteResult(rows=[])


_ONLYOFFICE_TEST_MODULE = None


def _load_content_library_module():
    fake_auth = ModuleType("app.api.auth")

    async def _fake_get_current_user():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    fake_auth.get_current_user = _fake_get_current_user

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock()),
        patch.dict(sys.modules, {"app.api.auth": fake_auth}),
    ):
        sys.modules.pop("app.api.content_library", None)
        return import_module("app.api.content_library")


def _load_dense_retriever_module():
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        qdrant_collection_prefix="tw_",
        rag_top_k_dense=5,
        qdrant_host="localhost",
        qdrant_port=6333,
        qdrant_api_key="",
    )

    fake_embedder = ModuleType("app.rag.embedder")

    class _FakeEmbedder:
        dimension = 3

    fake_embedder.Embedder = _FakeEmbedder

    fake_qdrant_client = ModuleType("qdrant_client")

    class _FakeQdrantClient:
        pass

    fake_qdrant_client.QdrantClient = _FakeQdrantClient
    fake_qdrant_client.models = SimpleNamespace()

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "app.rag.embedder": fake_embedder,
            "qdrant_client": fake_qdrant_client,
        },
    ):
        sys.modules.pop("app.rag.dense_retriever", None)
        return import_module("app.rag.dense_retriever")


def _load_engine_module():
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        qdrant_host="localhost",
        qdrant_port=6333,
        neo4j_uri="bolt://localhost:7687",
        chunk_min_size=100,
        chunk_max_size=400,
        llama_server_url="http://llama.test",
        llama_model="llama-test",
        llama_timeout=30,
    )

    fake_chunker = ModuleType("app.rag.chunker")

    class _FakeSemanticChunker:
        def __init__(self, embedder, min_chunk_size, max_chunk_size):
            self.embedder = embedder
            self.min_chunk_size = min_chunk_size
            self.max_chunk_size = max_chunk_size

    class _FakeChunkMetadata:
        pass

    class _FakeTextChunk:
        pass

    fake_chunker.SemanticChunker = _FakeSemanticChunker
    fake_chunker.ChunkMetadata = _FakeChunkMetadata
    fake_chunker.TextChunk = _FakeTextChunk

    fake_dense = ModuleType("app.rag.dense_retriever")

    class _FakeDenseRetriever:
        last_instance = None

        def __init__(self, embedder):
            self.embedder = embedder
            self.client = None
            self.load_calls: list[str] = []
            type(self).last_instance = self

        async def initialize(self):
            self.client = object()

        def load_persisted_chunks(self, collection: str = "documents"):
            self.load_calls.append(collection)
            return (
                ["Dense payload chunk A", "Dense payload chunk B"],
                [
                    {"document_id": 10, "source_file": "a.pdf"},
                    {"document_id": 11, "source_file": "b.pdf"},
                ],
            )

    fake_dense.DenseRetriever = _FakeDenseRetriever

    fake_embedder = ModuleType("app.rag.embedder")

    class _FakeEmbedder:
        pass

    def _fake_get_embedder():
        return _FakeEmbedder()

    fake_embedder.Embedder = _FakeEmbedder
    fake_embedder.get_embedder = _fake_get_embedder

    fake_fusion = ModuleType("app.rag.fusion")

    class _FakeRankFusion:
        pass

    fake_fusion.RankFusion = _FakeRankFusion

    fake_generator = ModuleType("app.rag.generator")

    class _FakeGenerator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeGenerationResult:
        pass

    fake_generator.Generator = _FakeGenerator
    fake_generator.GenerationResult = _FakeGenerationResult

    fake_graph = ModuleType("app.rag.graph_retriever")

    class _FakeGraphRetriever:
        async def initialize(self):
            return None

    fake_graph.GraphRetriever = _FakeGraphRetriever

    fake_reranker = ModuleType("app.rag.reranker")

    class _FakeReranker:
        pass

    fake_reranker.Reranker = _FakeReranker

    fake_sparse = ModuleType("app.rag.sparse_retriever")

    class _FakeSparseRetriever:
        last_instance = None

        def __init__(self):
            self.build_index_calls: list[tuple[list[str], list[dict]]] = []
            type(self).last_instance = self

        def build_index(self, texts: list[str], metadatas: list[dict]):
            self.build_index_calls.append((texts, metadatas))

    fake_sparse.SparseRetriever = _FakeSparseRetriever

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "app.rag.chunker": fake_chunker,
            "app.rag.dense_retriever": fake_dense,
            "app.rag.embedder": fake_embedder,
            "app.rag.fusion": fake_fusion,
            "app.rag.generator": fake_generator,
            "app.rag.graph_retriever": fake_graph,
            "app.rag.reranker": fake_reranker,
            "app.rag.sparse_retriever": fake_sparse,
        },
    ):
        sys.modules.pop("app.rag.engine", None)
        return import_module("app.rag.engine")


def _load_tasks_module():
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace()

    fake_celery = ModuleType("app.celery")

    class _FakeCeleryApp:
        def task(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    fake_celery.celery_app = _FakeCeleryApp()

    fake_database = ModuleType("app.db.database")
    fake_database.async_session_factory = Mock()

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "app.celery": fake_celery,
            "app.db.database": fake_database,
        },
    ):
        sys.modules.pop("app.tasks", None)
        return import_module("app.tasks")


def _extract_pdf_export_template() -> str:
    tasks_path = Path(__file__).resolve().parents[1] / "app" / "tasks.py"
    source = tasks_path.read_text(encoding="utf-8")
    template_block = source.split('template_str = """', 1)[1].split('                """', 1)[0]
    return dedent(template_block)


def _load_onlyoffice_module():
    global _ONLYOFFICE_TEST_MODULE
    if _ONLYOFFICE_TEST_MODULE is not None:
        return _ONLYOFFICE_TEST_MODULE

    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        minio_bucket="test-bucket",
        minio_endpoint="minio:9000",
        minio_access_key="minio-access",
        minio_secret_key="minio-secret",
        minio_secure=False,
        onlyoffice_ui_theme="theme-dark",
        onlyoffice_jwt_secret="onlyoffice-secret",
        onlyoffice_file_token_ttl_seconds=300,
        backend_public_url="http://backend.test",
        onlyoffice_url="http://onlyoffice.test",
        onlyoffice_internal_url="http://onlyoffice-internal.test",
    )

    fake_jwt = ModuleType("jwt")

    class _InvalidTokenError(Exception):
        pass

    def _jwt_default(value):
        if hasattr(value, "isoformat"):
            return {"__datetime__": value.isoformat()}
        raise TypeError(f"Unsupported value for fake jwt: {value!r}")

    def _encode(payload, secret, algorithm="HS256"):
        del secret, algorithm
        raw = json.dumps(payload, default=_jwt_default).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def _decode(token, secret, algorithms=None):
        del secret, algorithms
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive fake
            raise _InvalidTokenError(str(exc)) from exc

    fake_jwt.encode = _encode
    fake_jwt.decode = _decode
    fake_jwt.InvalidTokenError = _InvalidTokenError

    fake_docx = ModuleType("docx")

    class _FakeDocxDocument:
        def __init__(self, *args, **kwargs):
            self.paragraphs = []

        def add_paragraph(self, text=""):
            paragraph = SimpleNamespace(
                text=text, runs=[SimpleNamespace(font=SimpleNamespace(size=None))]
            )
            self.paragraphs.append(paragraph)
            return paragraph

        def save(self, target):
            if hasattr(target, "write"):
                target.write(b"")

    fake_docx.Document = _FakeDocxDocument

    fake_docx_shared = ModuleType("docx.shared")
    fake_docx_shared.Pt = lambda value: value

    fake_minio = ModuleType("minio")

    class _FakeMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket_name):
            return True

        def make_bucket(self, bucket_name):
            return None

        def get_object(self, bucket_name, object_name):
            return SimpleNamespace(
                read=lambda: b"",
                close=lambda: None,
                release_conn=lambda: None,
            )

        def put_object(self, *args, **kwargs):
            return None

        def remove_object(self, *args, **kwargs):
            return None

    fake_minio.Minio = _FakeMinio

    fake_minio_error = ModuleType("minio.error")

    class _FakeS3Error(Exception):
        def __init__(self, code="GenericError"):
            super().__init__(code)
            self.code = code

    fake_minio_error.S3Error = _FakeS3Error

    fake_db_database = ModuleType("app.db.database")

    async def _fake_get_db():
        return None

    fake_db_database.get_db = _fake_get_db

    fake_db_redis = ModuleType("app.db.redis")
    fake_db_redis.redis_client = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
        setex=AsyncMock(),
        delete=AsyncMock(),
    )

    fake_models = ModuleType("app.models")
    fake_models.Proposal = type("Proposal", (), {})
    fake_models.ProposalSection = type("ProposalSection", (), {})
    fake_models.ContentBlock = type("ContentBlock", (), {})

    fake_auth = ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return SimpleNamespace(id=1, name="Tester", email="tester@test.local")

    class _FakeUserResponse:
        pass

    fake_auth.get_current_user = _fake_get_current_user
    fake_auth.UserResponse = _FakeUserResponse

    fake_naming = ModuleType("app.utils.naming")
    fake_naming.sanitize_name = lambda value: value
    fake_naming.get_structured_minio_path = lambda *args, **kwargs: "structured/object.docx"

    fake_compliance = ModuleType("app.services.compliance_observability")

    async def _fake_sync_requirement_compliance_and_gate(*args, **kwargs):
        return None

    fake_compliance.sync_requirement_compliance_and_gate = (
        _fake_sync_requirement_compliance_and_gate
    )

    fake_kpi = ModuleType("app.services.kpi_reason_engine")
    fake_kpi.build_proposal_section_updated_event_payload = lambda *args, **kwargs: {}

    async def _fake_publish_domain_event(*args, **kwargs):
        return None

    async def _fake_sync_tender_and_publish_event(*args, **kwargs):
        return None

    fake_kpi.publish_domain_event = _fake_publish_domain_event
    fake_kpi.sync_tender_and_publish_event = _fake_sync_tender_and_publish_event

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "jwt": fake_jwt,
            "docx": fake_docx,
            "docx.shared": fake_docx_shared,
            "minio": fake_minio,
            "minio.error": fake_minio_error,
            "app.db.database": fake_db_database,
            "app.db.redis": fake_db_redis,
            "app.models": fake_models,
            "app.api.auth": fake_auth,
            "app.utils.naming": fake_naming,
            "app.services.compliance_observability": fake_compliance,
            "app.services.kpi_reason_engine": fake_kpi,
        },
    ):
        sys.modules.pop("app.api.onlyoffice", None)
        _ONLYOFFICE_TEST_MODULE = import_module("app.api.onlyoffice")
        return _ONLYOFFICE_TEST_MODULE


def _load_graph_retriever_module():
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test-password",
        rag_top_k_graph=5,
    )

    fake_neo4j = ModuleType("neo4j")

    class _FakeAsyncGraphDatabase:
        @staticmethod
        def driver(*args, **kwargs):
            return None

    fake_neo4j.AsyncGraphDatabase = _FakeAsyncGraphDatabase

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "neo4j": fake_neo4j,
        },
    ):
        sys.modules.pop("app.rag.graph_retriever", None)
        return import_module("app.rag.graph_retriever")


async def _read_streaming_response_body(response) -> bytes:
    return b"".join([chunk async for chunk in response.body_iterator])


def test_content_library_write_requires_authentication() -> None:
    """Anonymous callers should not be able to create reusable content blocks."""

    content_library_module = _load_content_library_module()

    app = FastAPI()
    app.include_router(content_library_module.router, prefix="/content-blocks")
    app.dependency_overrides[content_library_module.get_db] = lambda: _CreateOnlyDb()

    client = TestClient(app)

    response = client.post(
        "/content-blocks",
        json={
            "title": "Anonymous write attempt",
            "content": "This should be rejected without auth.",
            "category": "diagnostic",
            "tags": ["pre-fix"],
        },
    )

    assert response.status_code == 401


def test_content_library_authenticated_write_still_works() -> None:
    """Authenticated callers should still be able to create content blocks."""

    content_library_module = _load_content_library_module()

    app = FastAPI()
    app.include_router(content_library_module.router, prefix="/content-blocks")
    app.dependency_overrides[content_library_module.get_db] = lambda: _CreateOnlyDb()
    app.dependency_overrides[content_library_module.get_current_user] = lambda: SimpleNamespace(
        id=7,
        email="editor@test.local",
        role="editor",
    )

    client = TestClient(app)

    response = client.post(
        "/content-blocks",
        json={
            "title": "Authenticated write",
            "content": "This should succeed with auth.",
            "category": "diagnostic",
            "tags": ["regression"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Authenticated write"
    assert payload["content"] == "This should succeed with auth."


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/content-blocks", None),
        ("GET", "/content-blocks/1", None),
        (
            "PUT",
            "/content-blocks/1",
            {
                "title": "Unauthorized update",
                "content": "Should never reach handler.",
            },
        ),
        ("DELETE", "/content-blocks/1", None),
        ("POST", "/content-blocks/1/use", None),
    ],
)
def test_content_library_other_routes_require_authentication(
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    """Every exposed Content Library route should stay protected by auth."""

    content_library_module = _load_content_library_module()

    app = FastAPI()
    app.include_router(content_library_module.router, prefix="/content-blocks")
    app.dependency_overrides[content_library_module.get_db] = lambda: _CreateOnlyDb()

    client = TestClient(app)
    response = client.request(method, path, json=payload)

    assert response.status_code == 401


def test_content_library_search_escapes_ilike_wildcards() -> None:
    """Search terms containing %, _ and \\ should be escaped before ILIKE."""

    content_library_module = _load_content_library_module()
    db = _ListCaptureDb()
    search = "%admin_test\\"
    escaped_search = content_library_module._escape_ilike_search(search)

    asyncio.run(
        content_library_module.list_content_blocks(
            search=search,
            skip=0,
            limit=20,
            db=db,
        )
    )

    query_sql = str(
        db.statements[-1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    compiled_like_pattern = f"%{escaped_search}%".replace("\\", "\\\\").replace("%", "%%")

    assert escaped_search == "\\%admin\\_test\\\\"
    assert "ESCAPE '\\\\'" in query_sql
    assert compiled_like_pattern in query_sql


def test_dense_retriever_loads_persisted_chunks_from_qdrant_payloads() -> None:
    """Dense retriever should page through Qdrant payloads and extract text + metadata."""

    dense_retriever_module = _load_dense_retriever_module()
    retriever = dense_retriever_module.DenseRetriever(embedder=SimpleNamespace(dimension=3))

    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def scroll(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return (
                    [
                        SimpleNamespace(
                            payload={"text": "Alpha chunk", "document_id": 1, "section": "intro"}
                        ),
                        SimpleNamespace(payload={"document_id": 999}),
                        SimpleNamespace(payload={"text": "   ", "document_id": 888}),
                    ],
                    "page-2",
                )
            return (
                [
                    SimpleNamespace(payload={"text": "Beta chunk", "document_id": 2}),
                ],
                None,
            )

    retriever.client = _FakeClient()

    texts, metadatas = retriever.load_persisted_chunks(collection="documents", batch_size=2)

    assert texts == ["Alpha chunk", "Beta chunk"]
    assert metadatas == [
        {"document_id": 1, "section": "intro"},
        {"document_id": 2},
    ]
    assert retriever.client.calls[0]["collection_name"] == "tw_documents"
    assert retriever.client.calls[0]["with_payload"] is True
    assert retriever.client.calls[0]["with_vectors"] is False


def test_hybrid_rag_initialization_rebuilds_sparse_index() -> None:
    """Engine startup should rebuild BM25 from persisted dense payloads."""

    engine_module = _load_engine_module()
    engine = engine_module.HybridRAGEngine()

    asyncio.run(engine.initialize())

    assert engine._initialized is True
    assert engine.dense_retriever.load_calls == ["documents"]
    assert engine.sparse_retriever.build_index_calls == [
        (
            ["Dense payload chunk A", "Dense payload chunk B"],
            [
                {"document_id": 10, "source_file": "a.pdf"},
                {"document_id": 11, "source_file": "b.pdf"},
            ],
        )
    ]


def test_graph_retriever_search_uses_parameter_dicts_for_neo4j_queries() -> None:
    """Graph search should pass Cypher parameters via the dedicated Neo4j parameter dict."""

    graph_retriever_module = _load_graph_retriever_module()
    retriever = graph_retriever_module.GraphRetriever()

    class _FakeCursor:
        def __init__(self, records) -> None:
            self._records = records

        async def data(self):
            return self._records

    class _FakeSession:
        def __init__(self, records) -> None:
            self.records = records
            self.run_calls: list[dict] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, statement, parameters_=None, **kwargs):
            self.run_calls.append(
                {
                    "statement": statement,
                    "parameters_": parameters_,
                    "kwargs": kwargs,
                }
            )
            if kwargs:
                raise AssertionError(f"Unexpected Neo4j kwargs: {kwargs}")
            if parameters_ is None:
                raise AssertionError("Cypher parameters must be passed through parameters_.")
            return _FakeCursor(self.records)

    class _FakeDriver:
        def __init__(self, sessions: list[_FakeSession]) -> None:
            self._sessions = sessions

        def session(self):
            return self._sessions.pop(0)

    project_session = _FakeSession(
        [
            {
                "p": {
                    "id": "project-1",
                    "name": "Sanita Digitale",
                    "description": "Piattaforma per ospedali",
                    "category": "health",
                    "year": 2024,
                },
                "c": {"name": "ASL Roma"},
                "team": [{"name": "Mario Rossi", "role": "PM"}],
                "certifications": ["ISO 9001"],
            }
        ]
    )
    member_session = _FakeSession(
        [
            {
                "t": {
                    "id": "member-1",
                    "name": "Laura Bianchi",
                    "title": "Solution Architect",
                    "years_experience": 12,
                },
                "certifications": ["PMP"],
                "projects": [{"name": "Sanita Digitale", "role": "Architect"}],
            }
        ]
    )
    retriever._driver = _FakeDriver([project_session, member_session])

    results = asyncio.run(retriever.search("sanita", top_k=4))

    assert len(results) == 2
    assert project_session.run_calls[0]["parameters_"] == {"query": "sanita", "top_k": 4}
    assert project_session.run_calls[0]["kwargs"] == {}
    assert member_session.run_calls[0]["parameters_"] == {"query": "sanita", "top_k": 4}
    assert member_session.run_calls[0]["kwargs"] == {}
    assert results[0].entity_type == "Project"
    assert "Sanita Digitale" in results[0].text
    assert results[1].entity_type == "TeamMember"
    assert "Laura Bianchi" in results[1].text


def test_register_handler_does_not_refresh_user_after_commit() -> None:
    """Registration should not reintroduce redundant db.refresh(user) calls."""

    auth_path = Path(__file__).resolve().parents[1] / "app" / "api" / "auth.py"
    source = auth_path.read_text(encoding="utf-8")

    register_block = source.split("async def register(", 1)[1].split(
        '@router.post("/verify-otp"', 1
    )[0]

    assert "await db.commit()" in register_block
    assert "await db.refresh(user)" not in register_block


def test_sqlalchemy_models_do_not_use_mutable_default_literals() -> None:
    """ORM defaults should not use shared mutable literals like [] or {}."""

    models_path = Path(__file__).resolve().parents[1] / "app" / "models" / "__init__.py"
    source = models_path.read_text(encoding="utf-8")

    assert "default=[]" not in source
    assert "default={}" not in source


def test_backend_code_avoids_naive_datetime_calls() -> None:
    """The backend should avoid datetime.utcnow() and naive datetime.now()."""

    backend_root = Path(__file__).resolve().parents[1] / "app"
    python_files = list(backend_root.rglob("*.py"))

    offenders: list[str] = []
    for path in python_files:
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow(" in text:
            offenders.append(f"{path.name}: datetime.utcnow")

        for line in text.splitlines():
            if "datetime.now(" not in line:
                continue
            if "timezone.utc" in line:
                continue
            offenders.append(f"{path.name}: {line.strip()}")

    assert offenders == []


def test_proposal_update_reads_previous_status_safely_after_null_guard() -> None:
    """Proposal update should not dereference proposal.status before the null-safe expression."""

    proposals_path = Path(__file__).resolve().parents[1] / "app" / "api" / "proposals.py"
    source = proposals_path.read_text(encoding="utf-8")

    update_block = source.split("async def update_proposal(", 1)[1].split(
        "# ── Section Routes ──", 1
    )[0]

    assert "previous_status = proposal.status if proposal else None" in update_block
    assert "if not proposal:" in update_block


def test_section_update_normalizes_content_before_setattr() -> None:
    """Section updates should normalize content payloads before assigning to the model."""

    proposals_path = Path(__file__).resolve().parents[1] / "app" / "api" / "proposals.py"
    source = proposals_path.read_text(encoding="utf-8")

    update_section_block = source.split("async def update_section(", 1)[1].split(
        '@router.post("/{proposal_id}/sections"', 1
    )[0]

    assert 'if key == "content":' in update_section_block
    assert "value = _normalize_section_content(value)" in update_section_block
    assert "setattr(section, key, value)" in update_section_block


def test_pdf_export_template_escapes_all_untrusted_fields() -> None:
    """PDF export HTML should escape all untrusted proposal metadata and headings."""

    tasks_module = _load_tasks_module()
    tasks_source = (Path(__file__).resolve().parents[1] / "app" / "tasks.py").read_text(
        encoding="utf-8"
    )
    assert "select_autoescape(default=True, default_for_string=True)" in tasks_source

    template = Environment(
        autoescape=select_autoescape(default=True, default_for_string=True)
    ).from_string(_extract_pdf_export_template())

    rendered = template.render(
        proposal=SimpleNamespace(
            title='<script>alert("title")</script>',
            client="<img src=x onerror=\"alert('client')\">",
        ),
        sections=[
            {
                "title": "<svg onload=\"alert('section')\"></svg>",
                "safe_html": tasks_module._content_to_safe_pdf_html(
                    '<script>alert("body")</script>'
                ),
            }
        ],
    )

    assert '<script>alert("title")</script>' not in rendered
    assert "<img src=x onerror=\"alert('client')\">" not in rendered
    assert "<svg onload=\"alert('section')\"></svg>" not in rendered
    assert "&lt;script&gt;alert(&#34;title&#34;)&lt;/script&gt;" in rendered
    assert "&lt;img src=x onerror=&#34;alert(&#39;client&#39;)&#34;&gt;" in rendered
    assert "&lt;svg onload=&#34;alert(&#39;section&#39;)&#34;&gt;&lt;/svg&gt;" in rendered
    assert "&lt;script&gt;alert(&quot;body&quot;)&lt;/script&gt;" in rendered


def test_onlyoffice_file_download_rejects_token_for_wrong_owner() -> None:
    """A valid signature alone should not authorize file download for another owner."""

    onlyoffice_module = _load_onlyoffice_module()

    wrong_owner_token = onlyoffice_module._build_download_token(doc_key="doc-key-123", user_id=99)
    url = onlyoffice_module._build_signed_file_url("doc-key-123", download_token=wrong_owner_token)
    params = parse_qs(urlparse(url).query)

    fake_store = SimpleNamespace(get=AsyncMock(return_value=b"should-not-be-returned"))

    with (
        patch.object(
            onlyoffice_module,
            "get_session_metadata",
            AsyncMock(return_value={"object_name": "stored.docx", "owner_user_id": 7}),
        ),
        patch.object(onlyoffice_module, "_document_store", fake_store),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                onlyoffice_module.serve_document(
                    doc_key="doc-key-123",
                    expires=int(params["expires"][0]),
                    signature=params["signature"][0],
                    download_token=params["download_token"][0],
                )
            )

    assert exc_info.value.status_code == 403
    fake_store.get.assert_not_awaited()


def test_onlyoffice_file_download_succeeds_with_valid_signature_and_owner_token() -> None:
    """The signed download flow should still serve the file when both guards are valid."""

    onlyoffice_module = _load_onlyoffice_module()

    valid_token = onlyoffice_module._build_download_token(doc_key="doc-key-123", user_id=7)
    url = onlyoffice_module._build_signed_file_url("doc-key-123", download_token=valid_token)
    params = parse_qs(urlparse(url).query)

    fake_store = SimpleNamespace(get=AsyncMock(return_value=b"docx-binary"))

    with (
        patch.object(
            onlyoffice_module,
            "get_session_metadata",
            AsyncMock(return_value={"object_name": "stored.docx", "owner_user_id": 7}),
        ),
        patch.object(onlyoffice_module, "_document_store", fake_store),
    ):
        response = asyncio.run(
            onlyoffice_module.serve_document(
                doc_key="doc-key-123",
                expires=int(params["expires"][0]),
                signature=params["signature"][0],
                download_token=params["download_token"][0],
            )
        )
        body = asyncio.run(_read_streaming_response_body(response))

    assert response.status_code == 200
    assert response.media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == "attachment; filename=doc-key-123.docx"
    assert body == b"docx-binary"
    fake_store.get.assert_awaited_once_with("stored.docx")


def test_onlyoffice_callback_rejects_token_bound_to_another_document() -> None:
    """The callback endpoint should enforce the document-bound callback token."""

    onlyoffice_module = _load_onlyoffice_module()
    callback_token = onlyoffice_module.jwt.encode(
        {"document": {"key": "other-doc"}},
        onlyoffice_module.settings.onlyoffice_jwt_secret,
        algorithm="HS256",
    )
    payload = onlyoffice_module.CallbackPayload(
        key="doc-key-123",
        status=2,
        url="http://download.test/doc.docx",
        token=callback_token,
    )

    response = asyncio.run(
        onlyoffice_module.onlyoffice_callback(
            request=SimpleNamespace(method="POST"),
            payload=payload,
            db=SimpleNamespace(),
        )
    )

    assert response.status_code == 401
    assert json.loads(response.body.decode("utf-8")) == {"error": 1}


def test_onlyoffice_callback_get_probe_is_rejected() -> None:
    """The callback endpoint should not accept GET probes as successful callbacks."""

    onlyoffice_module = _load_onlyoffice_module()

    response = asyncio.run(
        onlyoffice_module.onlyoffice_callback(
            request=SimpleNamespace(method="GET"),
            payload=None,
            db=SimpleNamespace(),
        )
    )

    assert response.status_code == 405
    assert json.loads(response.body.decode("utf-8")) == {"error": 1}


def test_onlyoffice_cleanup_deletes_only_documents_older_than_utc_cutoff() -> None:
    """Cleanup should compare timestamps in UTC and delete only truly expired objects."""

    onlyoffice_module = _load_onlyoffice_module()
    store = onlyoffice_module.MinioDocumentStore()

    removed: list[tuple[str, str]] = []
    now_utc = datetime.now(timezone.utc)
    store.client = SimpleNamespace(
        list_objects=lambda bucket_name: [
            SimpleNamespace(
                object_name="expired.docx",
                last_modified=(now_utc - timedelta(hours=30)).astimezone(
                    timezone(timedelta(hours=2))
                ),
            ),
            SimpleNamespace(
                object_name="fresh.docx",
                last_modified=(now_utc - timedelta(hours=2)).astimezone(
                    timezone(timedelta(hours=-4))
                ),
            ),
            SimpleNamespace(object_name="unknown.docx", last_modified=None),
        ],
        remove_object=lambda bucket_name, object_name: removed.append((bucket_name, object_name)),
    )

    deleted_count = asyncio.run(store.cleanup_old_documents(max_age_hours=24))

    assert deleted_count == 1
    assert removed == [("test-bucket", "expired.docx")]
