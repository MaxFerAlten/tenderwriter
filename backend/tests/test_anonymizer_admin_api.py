import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

from app.api.anonymizer_admin import router
from app.api.auth import UserResponse, get_current_user
from app.db.database import get_db
from app.models import AnonymizerAuditLog, AppSettings


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
        self.settings_row = AppSettings(data={})
        self.audit_rows: list[AnonymizerAuditLog] = []
        self.add = self._add
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.execute = AsyncMock(side_effect=self._execute)

    def _add(self, row):
        if isinstance(row, AppSettings):
            self.settings_row = row
        elif isinstance(row, AnonymizerAuditLog):
            row.id = len(self.audit_rows) + 1
            self.audit_rows.append(row)

    async def _execute(self, stmt):
        stmt_str = str(stmt)
        if "anonymizer_audit_logs" in stmt_str:
            return _SequenceResult(self.audit_rows)
        return _ScalarResult(self.settings_row)


class AnonymizerAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/anonymizer")
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
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=1,
            email="admin@test.local",
            name="Admin",
            role="admin",
        )
        cls.db = _FakeDb()
        app.dependency_overrides[get_db] = lambda: cls.db
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.db.settings_row = AppSettings(data={})
        self.db.audit_rows = []
        self.db.commit.reset_mock()
        self.db.flush.reset_mock()

    def test_get_config_proxies_to_anonymizer_service(self) -> None:
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
            AsyncMock(return_value={"entities": ["PERSON"], "ttl_seconds": 3600}),
        ) as proxy_mock:
            response = self.client.get("/anonymizer/config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entities"], ["PERSON"])
        proxy_mock.assert_awaited_once_with("GET", "/v1/config")

    def test_test_endpoint_passes_payload_to_anonymizer(self) -> None:
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
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
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
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
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
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
        with patch(
            "app.api.anonymizer_admin.resolve_effective_privacy_policy",
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
            AnonymizerAuditLog(
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
