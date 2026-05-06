"""API-level tests for the system admin proxy backed by ops-agent."""

import os
import sys
import unittest
from importlib import import_module
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
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.services.ops_agent import OpsAgentClientResult


class _FakeUserResponse:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


_SYSTEM_TEST_MODULE = None


def _load_system_module():
    global _SYSTEM_TEST_MODULE
    if _SYSTEM_TEST_MODULE is not None:
        return _SYSTEM_TEST_MODULE

    fake_auth = import_module("types").ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return _FakeUserResponse(id=1, email="admin@test.local", name="Admin", role="admin")

    fake_auth.UserResponse = _FakeUserResponse
    fake_auth.get_current_user = _fake_get_current_user

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch.dict(sys.modules, {"app.api.auth": fake_auth}),
    ):
        sys.modules.pop("app.api.system", None)
        _SYSTEM_TEST_MODULE = import_module("app.api.system")
        return _SYSTEM_TEST_MODULE


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self) -> None:
        self.row = None
        self.add = Mock(side_effect=self._add)
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.execute = AsyncMock(side_effect=self._execute)

    def _add(self, row):
        self.row = row

    async def _execute(self, _stmt):
        return _ScalarResult(self.row)


class _MockOpsAgentClient:
    def __init__(
        self,
        *,
        capabilities_result: OpsAgentClientResult | None = None,
        containers_result: OpsAgentClientResult | None = None,
        logs_result: OpsAgentClientResult | None = None,
        stats_result: OpsAgentClientResult | None = None,
        nginx_result: OpsAgentClientResult | None = None,
    ) -> None:
        self.capabilities_result = capabilities_result or OpsAgentClientResult(
            True,
            200,
            {
                "available": True,
                "ops_monitoring": True,
                "nginx_hot_reload": True,
                "reason": None,
                "nginx_hot_reload_reason": None,
            },
        )
        self.containers_result = containers_result or OpsAgentClientResult(
            True,
            200,
            {
                "data": [
                    {"id": "abc123", "name": "backend", "status": "running", "health": "healthy"}
                ]
            },
        )
        self.logs_result = logs_result or OpsAgentClientResult(True, 200, {"logs": "line-1"})
        self.stats_result = stats_result or OpsAgentClientResult(
            True,
            200,
            {
                "cpu_percent": 12.5,
                "memory_usage_mb": 50.0,
                "memory_limit_mb": 100.0,
                "memory_percent": 50.0,
            },
        )
        self.nginx_result = nginx_result or OpsAgentClientResult(
            True,
            200,
            {"message": "Frontend nginx reloaded successfully"},
        )

    async def get_capabilities(self) -> OpsAgentClientResult:
        return self.capabilities_result

    async def list_containers(self) -> OpsAgentClientResult:
        return self.containers_result

    async def get_logs(self, container_name: str, *, tail: int = 100) -> OpsAgentClientResult:
        return self.logs_result

    async def get_stats(self, container_name: str) -> OpsAgentClientResult:
        return self.stats_result

    async def reload_frontend_nginx(self, payload: dict) -> OpsAgentClientResult:
        return self.nginx_result


class SystemApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.system_module = _load_system_module()
        cls.AppSettings = cls.system_module.AppSettings
        app = FastAPI()
        app.include_router(cls.system_module.router, prefix="/system")
        app.dependency_overrides[cls.system_module.get_current_user] = lambda: _FakeUserResponse(
            id=1,
            email="admin@test.local",
            name="Admin",
            role="admin",
        )
        cls.db = _FakeDb()
        app.dependency_overrides[cls.system_module.get_db] = lambda: cls.db
        cls.client = TestClient(app)

    def test_capabilities_degrade_cleanly_when_ops_agent_is_unavailable(self) -> None:
        mock_client = _MockOpsAgentClient(
            capabilities_result=OpsAgentClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message="Ops agent token is not configured.",
            )
        )
        with patch.object(self.system_module, "OpsAgentClient", return_value=mock_client):
            response = self.client.get("/system/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ops_agent"]["available"])
        self.assertFalse(payload["ops_monitoring"]["available"])
        self.assertEqual(payload["ops_agent"]["reason"], "Ops agent token is not configured.")

    def test_containers_endpoint_proxies_allowlisted_payload(self) -> None:
        mock_client = _MockOpsAgentClient()
        with patch.object(self.system_module, "OpsAgentClient", return_value=mock_client):
            response = self.client.get("/system/containers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "backend")

    def test_logs_endpoint_preserves_ops_agent_errors(self) -> None:
        mock_client = _MockOpsAgentClient(
            logs_result=OpsAgentClientResult(
                delivered=False,
                status_code=404,
                response_json={"detail": "Container 'tw-missing' not found"},
                error_message="Container 'tw-missing' not found",
            )
        )
        with patch.object(self.system_module, "OpsAgentClient", return_value=mock_client):
            response = self.client.get("/system/logs/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Container 'tw-missing' not found")

    def test_app_settings_persist_independently_from_live_nginx_apply(self) -> None:
        self.db.row = self.AppSettings(data={})
        mock_client = _MockOpsAgentClient(
            nginx_result=OpsAgentClientResult(
                delivered=False,
                status_code=503,
                response_json={"detail": "Ops agent unavailable"},
                error_message="Ops agent unavailable",
            )
        )
        with patch.object(self.system_module, "OpsAgentClient", return_value=mock_client):
            save_response = self.client.put(
                "/system/app-settings",
                json={
                    "rag_model": "Qwen 2.5",
                    "nginx_read_timeout": 111,
                    "nginx_connect_timeout": 222,
                    "nginx_send_timeout": 333,
                    "anonymizer_enabled": True,
                },
            )
            apply_response = self.client.post(
                "/system/nginx-timeout",
                json={
                    "read_timeout": 111,
                    "connect_timeout": 222,
                    "send_timeout": 333,
                },
            )

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["nginx_read_timeout"], 111)
        self.assertTrue(save_response.json()["anonymizer_enabled"])
        self.assertEqual(apply_response.status_code, 503)
        self.assertEqual(apply_response.json()["detail"], "Ops agent unavailable")


if __name__ == "__main__":
    unittest.main()
