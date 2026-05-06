"""Internal client for the privileged TenderWriter ops-agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass(slots=True)
class OpsAgentClientResult:
    """Normalized result for outbound ops-agent requests."""

    delivered: bool
    status_code: int | None
    response_json: dict[str, Any]
    error_message: str | None = None


class OpsAgentClient:
    """HTTP client for the internal privileged ops-agent service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_token: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ops_agent_base_url or "").rstrip("/")
        self.service_token = (
            service_token if service_token is not None else settings.ops_agent_token
        )
        self.timeout = timeout if timeout is not None else settings.ops_agent_timeout
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        token = (self.service_token or "").strip()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Service-Token": token,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> OpsAgentClientResult:
        if not self.base_url:
            return OpsAgentClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message="Ops agent base URL is not configured.",
            )

        if not (self.service_token or "").strip():
            return OpsAgentClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message="Ops agent token is not configured.",
            )

        request_kwargs: dict[str, Any] = {
            "headers": self._headers(),
            "params": params,
        }
        if payload is not None:
            request_kwargs["json"] = payload

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, **request_kwargs)
        except httpx.HTTPError as exc:
            return OpsAgentClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message=str(exc),
            )

        response_json = _safe_response_json(response)
        delivered = 200 <= response.status_code < 300
        error_message = (
            None
            if delivered
            else (response_json.get("detail") or f"Ops agent returned HTTP {response.status_code}")
        )
        return OpsAgentClientResult(
            delivered=delivered,
            status_code=response.status_code,
            response_json=response_json,
            error_message=error_message,
        )

    async def get_capabilities(self) -> OpsAgentClientResult:
        return await self._request("GET", "/capabilities")

    async def list_containers(self) -> OpsAgentClientResult:
        return await self._request("GET", "/containers")

    async def get_logs(self, container_name: str, *, tail: int = 100) -> OpsAgentClientResult:
        return await self._request("GET", f"/logs/{container_name}", params={"tail": tail})

    async def get_stats(self, container_name: str) -> OpsAgentClientResult:
        return await self._request("GET", f"/stats/{container_name}")

    async def reload_frontend_nginx(self, payload: dict[str, Any]) -> OpsAgentClientResult:
        return await self._request("POST", "/frontend/nginx-reload", payload=payload)


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return {"raw_text": text} if text else {}

    if isinstance(payload, dict):
        return payload
    return {"data": payload}
