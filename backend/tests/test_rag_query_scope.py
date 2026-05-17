"""Tests for /api/rag/query tender scoping and RBAC enforcement.

Covers Criticità A (tender_id/route_key validation) and audit list items
2 (invalid mode) and 3 (tender_id required for tender route).
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from test_module_loaders import load_rag_api_test_modules

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


_RAG_API_MODULES = load_rag_api_test_modules()
_RAG_MODULE = _RAG_API_MODULES.rag
RAGQueryRequest = _RAG_MODULE.RAGQueryRequest
rag_query = _RAG_MODULE.rag_query
QueryMode = _RAG_API_MODULES.engine.QueryMode


class _FakePolicy:
    route_key = "global"
    tender_id = None
    anonymizer_enabled = False
    target_base_url = None
    target_model = None
    target_provider = None
    target_api_key = None
    target_id = None
    target_timeout_ms = None
    mode = "internal"

    def as_dict(self) -> dict[str, object]:
        return {"mode": self.mode}


class _FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_calls = 0
        self.executed: list[object] = []
        self.execute_result = None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def execute(self, statement: object):
        self.executed.append(statement)
        return self.execute_result

    async def commit(self) -> None:
        self.commit_calls += 1


def _make_request_engine(answer: str = "Answer") -> SimpleNamespace:
    engine = SimpleNamespace(
        query=AsyncMock(
            return_value=SimpleNamespace(
                answer=answer,
                sources=[
                    {
                        "text": "fonte",
                        "score": 0.9,
                        "metadata": {"tender_id": 1},
                        "retriever_sources": ["dense"],
                        "source_scores": {"dense": 0.9},
                    }
                ],
                mode=QueryMode.QA,
                llm_route=None,
                anonymized=False,
            )
        )
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))


class RagQueryScopeTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, **request_kwargs):
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
        ):
            response = await rag_query(
                data=RAGQueryRequest(**request_kwargs),
                request=request,
                current_user=current_user,
                db=db,
            )
        return response, db

    async def test_invalid_mode_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await self._invoke(query="q", mode="bogus")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid mode", ctx.exception.detail)

    async def test_invalid_route_key_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await self._invoke(query="q", mode="qa", route_key="random")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("route_key", ctx.exception.detail)

    async def test_tender_route_without_tender_id_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await self._invoke(query="q", mode="qa", route_key="tender")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("tender_id", ctx.exception.detail)

    async def test_global_route_with_tender_id_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await self._invoke(query="q", mode="qa", route_key="global", tender_id=42)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("global", ctx.exception.detail)

    async def test_tender_route_calls_check_tender_access(self) -> None:
        check_mock = AsyncMock()
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
            patch.object(_RAG_MODULE, "check_tender_access", check_mock),
        ):
            await rag_query(
                data=RAGQueryRequest(query="q", mode="qa", route_key="tender", tender_id=99),
                request=request,
                current_user=current_user,
                db=db,
            )
        check_mock.assert_awaited_once()
        self.assertEqual(check_mock.call_args.args[0], 99)

    async def test_tender_access_denied_propagates_404(self) -> None:
        async def _deny(*args, **kwargs):
            raise HTTPException(status_code=404, detail="Tender not found")

        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
            patch.object(_RAG_MODULE, "check_tender_access", AsyncMock(side_effect=_deny)),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await rag_query(
                    data=RAGQueryRequest(query="q", mode="qa", route_key="tender", tender_id=99),
                    request=request,
                    current_user=current_user,
                    db=db,
                )
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_tender_id_forced_into_filters(self) -> None:
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
        ):
            await rag_query(
                data=RAGQueryRequest(
                    query="q",
                    mode="qa",
                    route_key="tender",
                    tender_id=99,
                    filters={"doc_type": "tender"},
                ),
                request=request,
                current_user=current_user,
                db=db,
            )
        forwarded = request.app.state.rag_engine.query.await_args.args[0]
        self.assertEqual(forwarded.filters, {"doc_type": "tender", "tender_id": 99})

    async def test_history_records_audit_columns(self) -> None:
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
        ):
            await rag_query(
                data=RAGQueryRequest(query="q", mode="qa", route_key="global"),
                request=request,
                current_user=current_user,
                db=db,
            )
        self.assertEqual(len(db.added), 1)
        history = db.added[0]
        self.assertEqual(getattr(history, "route_key", None), "global")
        self.assertIsNone(getattr(history, "tender_id", "not-set"))
        self.assertEqual(getattr(history, "anonymized", None), False)
        self.assertIsInstance(getattr(history, "settings_json", None), dict)
        sources = getattr(history, "sources_json", None)
        self.assertIsInstance(sources, list)
        self.assertEqual(sources[0]["retriever_sources"], ["dense"])
        self.assertEqual(getattr(history, "retrieval_version", None), "v1")

    async def test_rag_query_sets_active_profile_ids_from_tender_profile_id(self) -> None:
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        # _FakeDb.execute() returns the same result for every select() in the
        # handler (AppSettings loaders + the Tender lookup). The shared row must
        # therefore satisfy both: profile_id for the Tender path, and data=None
        # so the AppSettings loaders fall back to defaults (isinstance check).
        fake_tender = SimpleNamespace(id=99, profile_id="oscat_sct_toscana", data=None)
        db.execute_result = SimpleNamespace(scalar_one_or_none=lambda: fake_tender)
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
        ):
            await rag_query(
                data=RAGQueryRequest(
                    query="q",
                    mode="qa",
                    route_key="tender",
                    tender_id=99,
                ),
                request=request,
                current_user=current_user,
                db=db,
            )
        forwarded = request.app.state.rag_engine.query.await_args.args[0]
        self.assertEqual(forwarded.active_profile_ids, ("oscat_sct_toscana",))

    async def test_rag_query_without_tender_profile_id_keeps_empty_active_profiles(self) -> None:
        request = _make_request_engine()
        current_user = SimpleNamespace(id=7, role="user")
        db = _FakeDb()
        fake_tender = SimpleNamespace(id=99, profile_id=None, data=None)
        db.execute_result = SimpleNamespace(scalar_one_or_none=lambda: fake_tender)
        with (
            patch.object(
                _RAG_MODULE,
                "_resolve_runtime_privacy_policy",
                AsyncMock(return_value=_FakePolicy()),
            ),
            patch.object(_RAG_MODULE, "_audit_rag_result", AsyncMock()),
        ):
            await rag_query(
                data=RAGQueryRequest(
                    query="q",
                    mode="qa",
                    route_key="tender",
                    tender_id=99,
                ),
                request=request,
                current_user=current_user,
                db=db,
            )
        forwarded = request.app.state.rag_engine.query.await_args.args[0]
        self.assertEqual(forwarded.active_profile_ids, ())


if __name__ == "__main__":
    unittest.main()
