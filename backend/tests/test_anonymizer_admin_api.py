import os
import sys
import unittest
from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


class _FakeUserResponse:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeAppSettings:
    def __init__(self, data=None) -> None:
        self.data = data or {}


class _FakeColumn:
    def desc(self):
        return self


class _FakeAnonymizerAuditLog:
    created_at = _FakeColumn()

    def __init__(self, **kwargs) -> None:
        self.id = kwargs.pop("id", None)
        self.action = kwargs.pop("action", "")
        self.user_email = kwargs.pop("user_email", "")
        self.user_role = kwargs.pop("user_role", "")
        self.tender_id = kwargs.pop("tender_id", None)
        self.route_key = kwargs.pop("route_key", None)
        self.llm_route = kwargs.pop("llm_route", None)
        self.anonymized = kwargs.pop("anonymized", None)
        self.target_id = kwargs.pop("target_id", None)
        self.target_provider = kwargs.pop("target_provider", None)
        self.target_base_url = kwargs.pop("target_base_url", None)
        self.session_token = kwargs.pop("session_token", None)
        self.success = kwargs.pop("success", True)
        self.error_message = kwargs.pop("error_message", None)
        self.payload_json = kwargs.pop("payload_json", None)
        self.created_at = kwargs.pop("created_at", None)
        for key, value in kwargs.items():
            setattr(self, key, value)


def _default_policy_payload() -> dict:
    return {
        "default": {},
        "routes": {},
        "tenders": {},
    }


_ANON_ADMIN_TEST_MODULE = None


class _FakeSelect:
    def __init__(self, model) -> None:
        self.model = model

    def order_by(self, *args, **kwargs):
        del args, kwargs
        return self

    def limit(self, *args, **kwargs):
        del args, kwargs
        return self

    def __str__(self) -> str:
        return getattr(self.model, "__name__", str(self.model))


def _fake_select(model):
    return _FakeSelect(model)


def _load_anonymizer_admin_module():
    global _ANON_ADMIN_TEST_MODULE
    if _ANON_ADMIN_TEST_MODULE is not None:
        return _ANON_ADMIN_TEST_MODULE

    fake_auth = ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return _FakeUserResponse(id=1, email="admin@test.local", name="Admin", role="admin")

    fake_auth.UserResponse = _FakeUserResponse
    fake_auth.get_current_user = _fake_get_current_user

    fake_db_database = ModuleType("app.db.database")

    async def _fake_get_db():
        return None

    fake_db_database.get_db = _fake_get_db

    fake_models = ModuleType("app.models")
    fake_models.AppSettings = _FakeAppSettings
    fake_models.AnonymizerAuditLog = _FakeAnonymizerAuditLog

    fake_privacy_audit = ModuleType("app.privacy_audit")

    async def _fake_persist_privacy_audit(
        *,
        db,
        action,
        current_user,
        payload=None,
        success=True,
        tender_id=None,
        route_key=None,
        llm_route=None,
        anonymized=None,
        target_id=None,
        target_provider=None,
        target_base_url=None,
        session_id=None,
        session_token=None,
        error_message=None,
        **extra,
    ):
        del extra
        db.add(
            _FakeAnonymizerAuditLog(
                action=action,
                user_email=current_user.email,
                user_role=current_user.role,
                tender_id=tender_id,
                route_key=route_key,
                llm_route=llm_route,
                anonymized=anonymized,
                target_id=target_id,
                target_provider=target_provider,
                target_base_url=target_base_url,
                session_token=session_token or session_id,
                success=success,
                error_message=error_message,
                payload_json=payload or {},
            )
        )

    fake_privacy_audit.persist_privacy_audit = _fake_persist_privacy_audit

    fake_privacy_policy = ModuleType("app.privacy_policy")

    async def _fake_load_privacy_policy_document(db):
        payload = _default_policy_payload()
        data = getattr(getattr(db, "settings_row", None), "data", {}) or {}
        policy = data.get("anonymizer_policy")
        if isinstance(policy, dict):
            payload.update(policy)
        return payload

    async def _fake_resolve_effective_privacy_policy(
        db,
        *,
        route_key="tender",
        tender_id=None,
        anonymizer_enabled_override=None,
    ):
        del db, anonymizer_enabled_override
        return SimpleNamespace(
            as_dict=lambda: {
                "route_key": route_key,
                "tender_id": tender_id,
                "mode": "internal_only",
                "anonymizer_enabled": False,
                "target_id": None,
                "target_provider": None,
                "target_base_url": None,
                "sources": [],
            }
        )

    fake_privacy_policy.load_privacy_policy_document = _fake_load_privacy_policy_document
    fake_privacy_policy.resolve_effective_privacy_policy = _fake_resolve_effective_privacy_policy

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch.dict(
            sys.modules,
            {
                "app.api.auth": fake_auth,
                "app.db.database": fake_db_database,
                "app.models": fake_models,
                "app.privacy_audit": fake_privacy_audit,
                "app.privacy_policy": fake_privacy_policy,
            },
        ),
    ):
        sys.modules.pop("app.api.anonymizer_admin", None)
        _ANON_ADMIN_TEST_MODULE = import_module("app.api.anonymizer_admin")
        _ANON_ADMIN_TEST_MODULE.select = _fake_select
        return _ANON_ADMIN_TEST_MODULE


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _SequenceResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._values))


class _FakeDb:
    def __init__(self) -> None:
        self.settings_row = _FakeAppSettings(data={})
        self.audit_rows: list[_FakeAnonymizerAuditLog] = []
        self.add = self._add
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.execute = AsyncMock(side_effect=self._execute)

    def _add(self, row):
        if isinstance(row, _FakeAppSettings):
            self.settings_row = row
        elif isinstance(row, _FakeAnonymizerAuditLog):
            row.id = len(self.audit_rows) + 1
            self.audit_rows.append(row)

    async def _execute(self, stmt):
        model = getattr(stmt, "model", None)
        if model is _FakeAnonymizerAuditLog or "AnonymizerAuditLog" in str(stmt):
            return _SequenceResult(self.audit_rows)
        return _ScalarResult(self.settings_row)


class AnonymizerAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin_module = _load_anonymizer_admin_module()
        app = FastAPI()
        app.include_router(cls.admin_module.router, prefix="/anonymizer")
        app.state.rag_engine = type(
            "FakeRagEngine",
            (),
            {
                "get_anonymizer_runtime_stats": lambda self: {"fallback_events": 2, "circuit_open": False},
                "get_last_privacy_debug_trace": lambda self: {
                    "timestamp": "2026-03-27T10:30:00+00:00",
                    "mode": "qa",
                    "route_key": "tender",
                    "tender_id": 42,
                    "llm_route": "external_anonymized",
                    "anonymizer_enabled": True,
                    "anonymized": True,
                    "session_token": "sess...1234",
                    "target_id": 7,
                    "target_provider": "openai",
                    "target_base_url": "https://llm.example.com/v1",
                    "anonymized_prompt_variables": {"query": "Chi e [PERSONA_1]?"},
                    "note": "external route uses anonymized prompt variables",
                },
            },
        )()
        app.dependency_overrides[cls.admin_module.get_current_user] = lambda: _FakeUserResponse(
            id=1,
            email="admin@test.local",
            name="Admin",
            role="admin",
        )
        cls.db = _FakeDb()
        app.dependency_overrides[cls.admin_module.get_db] = lambda: cls.db
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.db.settings_row = _FakeAppSettings(data={})
        self.db.audit_rows = []
        self.db.commit.reset_mock()
        self.db.flush.reset_mock()

    def test_get_config_proxies_to_anonymizer_service(self) -> None:
        with patch.object(
            self.admin_module,
            "_proxy_anonymizer",
            AsyncMock(return_value={"entities": ["PERSON"], "ttl_seconds": 3600}),
        ) as proxy_mock:
            response = self.client.get("/anonymizer/config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entities"], ["PERSON"])
        proxy_mock.assert_awaited_once_with("GET", "/v1/config")

    def test_test_endpoint_passes_payload_to_anonymizer(self) -> None:
        with patch.object(
            self.admin_module,
            "_proxy_anonymizer",
            AsyncMock(return_value={"session_id": "sess-1", "chunks": []}),
        ) as proxy_mock:
            response = self.client.post(
                "/anonymizer/test",
                json={"text": "Mario Rossi", "config": {"entities": ["PERSON"]}},
            )

        self.assertEqual(response.status_code, 200)
        proxy_mock.assert_awaited_once_with(
            "POST",
            "/v1/anonymize",
            {"text": "Mario Rossi", "config": {"entities": ["PERSON"]}},
        )
        self.assertEqual(self.db.audit_rows[-1].action, "anonymizer_test")

    def test_stats_endpoint_merges_runtime_metrics(self) -> None:
        with patch.object(
            self.admin_module,
            "_proxy_anonymizer",
            AsyncMock(return_value={"requests": 4, "sessions": 2}),
        ):
            response = self.client.get("/anonymizer/stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requests"], 4)
        self.assertEqual(response.json()["fallback_events"], 2)

    def test_debug_endpoint_returns_last_rag_trace(self) -> None:
        response = self.client.get("/anonymizer/debug/last-rag")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["llm_route"], "external_anonymized")
        self.assertEqual(
            response.json()["anonymized_prompt_variables"]["query"],
            "Chi e [PERSONA_1]?",
        )

    def test_deanonymize_endpoint_proxies_payload(self) -> None:
        with patch.object(
            self.admin_module,
            "_proxy_anonymizer",
            AsyncMock(return_value={"text": "Mario Rossi", "mapping_size": 1, "session_id": "sess-1"}),
        ) as proxy_mock:
            response = self.client.post(
                "/anonymizer/deanonymize",
                json={"text": "[PERSONA_1]", "session_id": "sess-1"},
            )

        self.assertEqual(response.status_code, 200)
        proxy_mock.assert_awaited_once_with(
            "POST",
            "/v1/deanonymize",
            {"text": "[PERSONA_1]", "session_id": "sess-1"},
        )
        self.assertEqual(self.db.audit_rows[-1].action, "anonymizer_deanonymize")

    def test_policy_roundtrip_uses_app_settings_storage(self) -> None:
        response = self.client.put(
            "/anonymizer/policy",
            json={
                "default": {"mode": "external_anonymized"},
                "routes": {"opencode": {"mode": "internal_only"}},
                "tenders": {"42": {"anonymizer_enabled": True}},
            },
        )
        follow_up = self.client.get("/anonymizer/policy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["default"]["mode"], "external_anonymized")
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(follow_up.json()["routes"]["opencode"]["mode"], "internal_only")
        self.assertEqual(self.db.audit_rows[-1].action, "anonymizer_policy_update")

    def test_effective_policy_endpoint_returns_resolved_policy(self) -> None:
        with patch.object(
            self.admin_module,
            "resolve_effective_privacy_policy",
            AsyncMock(
                return_value=SimpleNamespace(
                    as_dict=lambda: {
                        "route_key": "tender",
                        "tender_id": 42,
                        "mode": "external_anonymized",
                        "anonymizer_enabled": True,
                        "target_id": 7,
                        "target_provider": "openai",
                        "target_base_url": "https://llm.example.com/v1",
                        "sources": ["gateway.active_target"],
                    }
                )
            ),
        ):
            response = self.client.get("/anonymizer/policy/effective?route_key=tender&tender_id=42")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_id"], 7)
        self.assertEqual(response.json()["mode"], "external_anonymized")

    def test_audit_endpoint_lists_recent_entries(self) -> None:
        self.db.audit_rows = [
            _FakeAnonymizerAuditLog(
                id=1,
                action="rag_query",
                user_email="admin@test.local",
                user_role="admin",
                success=True,
                payload_json={"mode": "qa"},
            )
        ]

        response = self.client.get("/anonymizer/audit")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["action"], "rag_query")


if __name__ == "__main__":
    unittest.main()
