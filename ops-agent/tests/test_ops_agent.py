import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from fastapi.testclient import TestClient
    _TEST_CLIENT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only in minimal test environments.
    TestClient = None  # type: ignore[assignment]
    _TEST_CLIENT_IMPORT_ERROR = exc

os.environ.setdefault("OPS_AGENT_TOKEN", "ops-agent-token-123")

from app.config import settings
from app.docker_ops import ContainerAccessError, DockerOpsService, NginxReloadError
from app.main import app


class _FakeContainer:
    def __init__(self, *, name: str, short_id: str = "abc123", status: str = "running", health: str = "healthy") -> None:
        self.name = name
        self.short_id = short_id
        self.status = status
        self.attrs = {"State": {"Health": {"Status": health}}}
        self.exec_run = Mock(return_value=(0, b""))

    def logs(self, **_: object) -> bytes:
        return b"2026-03-20T12:00:00Z hello"

    def stats(self, **_: object) -> dict[str, object]:
        return {
            "cpu_stats": {"cpu_usage": {"total_usage": 20}, "system_cpu_usage": 100, "online_cpus": 2},
            "precpu_stats": {"cpu_usage": {"total_usage": 10}, "system_cpu_usage": 80},
            "memory_stats": {"usage": 52428800, "limit": 104857600},
        }


class _FakeContainersApi:
    def __init__(self, mapping: dict[str, _FakeContainer]) -> None:
        self.mapping = mapping

    def list(self, **_: object) -> list[_FakeContainer]:
        return list(self.mapping.values())

    def get(self, name: str) -> _FakeContainer:
        if name not in self.mapping:
            raise KeyError(name)
        return self.mapping[name]


class _FakeDockerClient:
    def __init__(self, mapping: dict[str, _FakeContainer]) -> None:
        self.containers = _FakeContainersApi(mapping)

    def ping(self) -> bool:
        return True


class DockerOpsServiceTests(unittest.TestCase):
    def test_normalize_container_name_enforces_safe_names(self) -> None:
        service = DockerOpsService(allowed_prefix="tw-", frontend_container="tw-frontend", client=object())

        self.assertEqual(service._normalize_container_name("frontend"), "tw-frontend")
        self.assertEqual(service._normalize_container_name("tw-backend"), "tw-backend")
        with self.assertRaises(ContainerAccessError):
            service._normalize_container_name("../../etc/passwd")

    def test_list_containers_filters_non_allowlisted_names(self) -> None:
        client = _FakeDockerClient(
            {
                "tw-backend": _FakeContainer(name="tw-backend"),
                "other-service": _FakeContainer(name="other-service"),
            }
        )
        service = DockerOpsService(allowed_prefix="tw-", frontend_container="tw-frontend", client=client)

        items = service.list_containers()

        self.assertEqual(items, [{"id": "abc123", "name": "backend", "status": "running", "health": "healthy"}])

    def test_reload_frontend_uses_fixed_container(self) -> None:
        frontend = _FakeContainer(name="tw-frontend")
        client = _FakeDockerClient({"tw-frontend": frontend})
        service = DockerOpsService(allowed_prefix="tw-", frontend_container="tw-frontend", client=client)

        result = service.reload_frontend_nginx(read_timeout=30, connect_timeout=31, send_timeout=32)

        self.assertEqual(result["container"], "tw-frontend")
        command = frontend.exec_run.call_args.args[0]
        self.assertIn("proxy_read_timeout 30;", command)
        self.assertIn("proxy_connect_timeout 31;", command)
        self.assertIn("proxy_send_timeout 32;", command)

    def test_capabilities_disable_nginx_hot_reload_when_conf_is_missing(self) -> None:
        frontend = _FakeContainer(name="tw-frontend")
        frontend.exec_run = Mock(return_value=(1, b""))
        client = _FakeDockerClient({"tw-frontend": frontend})
        service = DockerOpsService(allowed_prefix="tw-", frontend_container="tw-frontend", client=client)

        result = service.capabilities()

        self.assertTrue(result["available"])
        self.assertFalse(result["nginx_hot_reload"])
        self.assertIn("hot reload is unavailable", result["nginx_hot_reload_reason"])

    def test_reload_frontend_raises_when_nginx_conf_is_missing(self) -> None:
        frontend = _FakeContainer(name="tw-frontend")

        def _exec_run(command: str):
            if "test -f" in command:
                return 1, b""
            return 0, b""

        frontend.exec_run = Mock(side_effect=_exec_run)
        client = _FakeDockerClient({"tw-frontend": frontend})
        service = DockerOpsService(allowed_prefix="tw-", frontend_container="tw-frontend", client=client)

        with self.assertRaises(NginxReloadError):
            service.reload_frontend_nginx(read_timeout=30, connect_timeout=31, send_timeout=32)


class OpsAgentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TestClient is None:
            raise unittest.SkipTest(
                f"fastapi TestClient unavailable in this environment: {_TEST_CLIENT_IMPORT_ERROR}"
            )
        cls.client = TestClient(app)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.ops_agent_token}"}

    def test_requires_service_token(self) -> None:
        response = self.client.get("/containers")
        self.assertEqual(response.status_code, 401)

    def test_capabilities_endpoint_returns_allowlisted_capabilities(self) -> None:
        fake_service = SimpleNamespace(capabilities=Mock(return_value={
            "service": "tw-ops-agent",
            "available": True,
            "ops_monitoring": True,
            "nginx_hot_reload": True,
            "allowed_prefix": "tw-",
            "frontend_container": "tw-frontend",
            "reason": None,
            "nginx_hot_reload_reason": None,
        }))
        with patch("app.main.ops_service", fake_service):
            response = self.client.get("/capabilities", headers=self._headers())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ops_monitoring"])

    def test_logs_endpoint_maps_service_errors(self) -> None:
        fake_service = SimpleNamespace(get_logs=Mock(side_effect=ContainerAccessError("Invalid container name")))
        with patch("app.main.ops_service", fake_service):
            response = self.client.get("/logs/not-valid", headers=self._headers())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Invalid container name")


if __name__ == "__main__":
    unittest.main()
