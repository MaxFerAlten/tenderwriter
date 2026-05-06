import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
clear_search_history = _RAG_MODULE.clear_search_history
rag_query = _RAG_MODULE.rag_query
QueryMode = _RAG_API_MODULES.engine.QueryMode


class _FakePolicy:
    route_key = "tender"
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
        self.execute_result = None
        self.executed: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def execute(self, statement: object):
        self.executed.append(statement)
        return self.execute_result

    async def commit(self) -> None:
        self.commit_calls += 1


class _FakeDeleteResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class RagHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def _collect_streaming_body(self, response) -> str:
        chunks: list[str] = []
        async for item in response.body_iterator:
            if isinstance(item, bytes):
                chunks.append(item.decode("utf-8"))
            else:
                chunks.append(str(item))
        return "".join(chunks)

    async def test_query_does_not_persist_history_when_disabled(self) -> None:
        engine = SimpleNamespace(
            query=AsyncMock(
                return_value=SimpleNamespace(
                    answer="Answer",
                    sources=[],
                    mode=QueryMode.SEARCH,
                    llm_route=None,
                    anonymized=False,
                )
            )
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))
        current_user = SimpleNamespace(id=7)
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
                data=RAGQueryRequest(query="assignment", mode="search", save_history=False),
                request=request,
                current_user=current_user,
                db=db,
            )

        self.assertEqual(response.answer, "Answer")
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_calls, 1)

    async def test_query_persists_history_by_default(self) -> None:
        engine = SimpleNamespace(
            query=AsyncMock(
                return_value=SimpleNamespace(
                    answer="Answer",
                    sources=[],
                    mode=QueryMode.SEARCH,
                    llm_route=None,
                    anonymized=False,
                )
            )
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))
        current_user = SimpleNamespace(id=7)
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
                data=RAGQueryRequest(query="assignment", mode="search"),
                request=request,
                current_user=current_user,
                db=db,
            )

        self.assertEqual(len(db.added), 1)
        self.assertEqual(getattr(db.added[0], "query", None), "assignment")
        self.assertEqual(db.commit_calls, 1)

    async def test_query_forwards_retriever_settings_to_engine(self) -> None:
        engine = SimpleNamespace(
            query=AsyncMock(
                return_value=SimpleNamespace(
                    answer="Answer",
                    sources=[],
                    mode=QueryMode.SEARCH,
                    llm_route=None,
                    anonymized=False,
                )
            )
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))
        current_user = SimpleNamespace(id=7)
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
                    query="assignment",
                    mode="search",
                    top_k=8,
                    retrieval_top_k=24,
                    temperature=0.45,
                    save_history=False,
                    retrievers={"dense": True, "sparse": False, "graph": True},
                    fusion_weights={"dense": 0.55, "sparse": 0.2, "graph": 0.45},
                ),
                request=request,
                current_user=current_user,
                db=db,
            )

        forwarded = engine.query.await_args.args[0]
        self.assertEqual(forwarded.top_k, 8)
        self.assertEqual(forwarded.retrieval_top_k, 24)
        self.assertEqual(forwarded.temperature, 0.45)
        self.assertEqual(forwarded.retrievers, {"dense": True, "sparse": False, "graph": True})
        self.assertEqual(forwarded.fusion_weights, {"dense": 0.55, "sparse": 0.2, "graph": 0.45})

    async def test_stream_query_persists_history_when_generation_succeeds(self) -> None:
        async def _fake_query_stream(_rag_query):
            yield "Prima parte"
            yield " finale"

        engine = SimpleNamespace(query_stream=_fake_query_stream)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))
        current_user = SimpleNamespace(id=7)
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
                data=RAGQueryRequest(query="assignment", mode="qa", stream=True),
                request=request,
                current_user=current_user,
                db=db,
            )

        body = await self._collect_streaming_body(response)
        self.assertIn("data: Prima parte", body)
        self.assertIn("data:  finale", body)
        self.assertIn("data: [DONE]", body)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(getattr(db.added[0], "response", None), "Prima parte finale")
        self.assertEqual(db.commit_calls, 1)

    async def test_stream_query_emits_structured_error_and_skips_history_on_generation_failure(
        self,
    ) -> None:
        async def _failing_query_stream(_rag_query):
            raise RuntimeError("NoValidHarFileError: No .har file found")
            yield  # pragma: no cover

        engine = SimpleNamespace(query_stream=_failing_query_stream)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=engine)))
        current_user = SimpleNamespace(id=7)
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
                data=RAGQueryRequest(query="assignment", mode="qa", stream=True),
                request=request,
                current_user=current_user,
                db=db,
            )

        body = await self._collect_streaming_body(response)
        self.assertIn('"type": "error"', body)
        self.assertIn("NoValidHarFileError: No .har file found", body)
        self.assertIn("data: [DONE]", body)
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_calls, 1)

    async def test_clear_search_history_deletes_only_current_user_rows(self) -> None:
        db = _FakeDb()
        db.execute_result = _FakeDeleteResult(rowcount=4)
        current_user = SimpleNamespace(id=7)

        response = await clear_search_history(
            current_user=current_user,
            db=db,
        )

        self.assertEqual(response, {"deleted": 4})
        self.assertEqual(len(db.executed), 1)
        self.assertEqual(db.commit_calls, 1)


if __name__ == "__main__":
    unittest.main()
