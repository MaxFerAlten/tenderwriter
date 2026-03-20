"""Allowlisted Docker operations for the internal ops agent."""

from __future__ import annotations

import re
from typing import Any

import docker


SAFE_CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker API is unavailable."""


class ContainerAccessError(RuntimeError):
    """Raised when a caller asks for a disallowed container."""


class ContainerNotFoundError(RuntimeError):
    """Raised when a container is not found."""


class NginxReloadError(RuntimeError):
    """Raised when the frontend Nginx reload fails."""


class DockerOpsService:
    """Small allowlisted wrapper around the Docker SDK."""

    def __init__(
        self,
        *,
        allowed_prefix: str,
        frontend_container: str,
        client: Any | None = None,
    ) -> None:
        self.allowed_prefix = allowed_prefix
        self.frontend_container = frontend_container
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            self._client = docker.from_env()
        except Exception as exc:
            raise DockerUnavailableError(f"Docker API unavailable: {exc}") from exc
        return self._client

    def _normalize_container_name(self, container_name: str) -> str:
        raw_name = (container_name or "").strip()
        if not raw_name or not SAFE_CONTAINER_NAME_RE.match(raw_name):
            raise ContainerAccessError("Invalid container name")
        if raw_name.startswith(self.allowed_prefix):
            return raw_name
        return f"{self.allowed_prefix}{raw_name}"

    def _get_container(self, container_name: str) -> Any:
        full_name = self._normalize_container_name(container_name)
        client = self._get_client()
        try:
            return client.containers.get(full_name)
        except docker.errors.NotFound as exc:
            raise ContainerNotFoundError(f"Container '{full_name}' not found") from exc
        except Exception as exc:
            raise DockerUnavailableError(f"Unable to reach Docker API: {exc}") from exc

    def capabilities(self) -> dict[str, Any]:
        try:
            client = self._get_client()
            client.ping()
        except DockerUnavailableError as exc:
            return {
                "service": "tw-ops-agent",
                "available": False,
                "ops_monitoring": False,
                "nginx_hot_reload": False,
                "reason": str(exc),
            }
        except Exception as exc:
            return {
                "service": "tw-ops-agent",
                "available": False,
                "ops_monitoring": False,
                "nginx_hot_reload": False,
                "reason": f"Docker API unavailable: {exc}",
            }

        nginx_available = True
        nginx_reason: str | None = None
        try:
            client.containers.get(self.frontend_container)
        except docker.errors.NotFound:
            nginx_available = False
            nginx_reason = f"Frontend container '{self.frontend_container}' not found"
        except Exception as exc:
            nginx_available = False
            nginx_reason = f"Unable to inspect frontend container: {exc}"

        return {
            "service": "tw-ops-agent",
            "available": True,
            "ops_monitoring": True,
            "nginx_hot_reload": nginx_available,
            "allowed_prefix": self.allowed_prefix,
            "frontend_container": self.frontend_container,
            "reason": None,
            "nginx_hot_reload_reason": nginx_reason,
        }

    def list_containers(self) -> list[dict[str, Any]]:
        client = self._get_client()
        try:
            containers = client.containers.list(all=True, filters={"name": self.allowed_prefix})
        except Exception as exc:
            raise DockerUnavailableError(f"Unable to list containers: {exc}") from exc

        items = []
        for container in containers:
            name = getattr(container, "name", "")
            if not name.startswith(self.allowed_prefix):
                continue
            items.append(
                {
                    "id": container.short_id,
                    "name": name.replace(self.allowed_prefix, "", 1),
                    "status": container.status,
                    "health": container.attrs.get("State", {}).get("Health", {}).get("Status", "unknown"),
                }
            )
        return sorted(items, key=lambda item: item["name"])

    def get_logs(self, container_name: str, tail: int = 100) -> dict[str, Any]:
        container = self._get_container(container_name)
        try:
            logs = container.logs(
                tail=max(1, tail),
                stdout=True,
                stderr=True,
                timestamps=True,
            ).decode("utf-8")
        except Exception as exc:
            raise DockerUnavailableError(f"Unable to fetch container logs: {exc}") from exc
        return {"logs": logs}

    def get_stats(self, container_name: str) -> dict[str, Any]:
        container = self._get_container(container_name)
        try:
            stats = container.stats(stream=False)
        except Exception as exc:
            raise DockerUnavailableError(f"Unable to fetch container stats: {exc}") from exc

        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_cpu_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        num_cpus = stats["cpu_stats"]["online_cpus"]
        cpu_percent = 0.0
        if system_cpu_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / system_cpu_delta) * num_cpus * 100.0

        mem_usage = stats["memory_stats"].get("usage", 0)
        mem_limit = stats["memory_stats"].get("limit", 1)
        mem_percent = (mem_usage / mem_limit) * 100.0

        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_usage / (1024 * 1024), 2),
            "memory_limit_mb": round(mem_limit / (1024 * 1024), 2),
            "memory_percent": round(mem_percent, 2),
        }

    def reload_frontend_nginx(
        self,
        *,
        read_timeout: int,
        connect_timeout: int,
        send_timeout: int,
    ) -> dict[str, Any]:
        client = self._get_client()
        try:
            frontend_container = client.containers.get(self.frontend_container)
        except docker.errors.NotFound as exc:
            raise ContainerNotFoundError(f"Container '{self.frontend_container}' not found") from exc
        except Exception as exc:
            raise DockerUnavailableError(f"Unable to reach Docker API: {exc}") from exc

        commands = [
            f"sed -i -E 's/proxy_read_timeout [0-9]+;/proxy_read_timeout {read_timeout};/' /etc/nginx/conf.d/default.conf",
            f"sed -i -E 's/proxy_connect_timeout [0-9]+;/proxy_connect_timeout {connect_timeout};/' /etc/nginx/conf.d/default.conf",
            f"sed -i -E 's/proxy_send_timeout [0-9]+;/proxy_send_timeout {send_timeout};/' /etc/nginx/conf.d/default.conf",
            "nginx -s reload",
        ]
        full_command = "sh -c \"" + " && ".join(commands) + "\""
        exit_code, output = frontend_container.exec_run(full_command)
        if exit_code != 0:
            decoded_output = output.decode("utf-8") if isinstance(output, (bytes, bytearray)) else str(output)
            raise NginxReloadError(f"Failed to reload nginx: {decoded_output}")

        return {
            "message": "Frontend nginx reloaded successfully",
            "container": self.frontend_container,
            "timeouts": {
                "read_timeout": read_timeout,
                "connect_timeout": connect_timeout,
                "send_timeout": send_timeout,
            },
        }
