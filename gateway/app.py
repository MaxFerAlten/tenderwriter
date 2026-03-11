import os
import asyncio
from typing import Callable

import httpx
from fastapi import FastAPI, Request, Response
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway configuration loaded from environment."""

    model_config = ConfigDict(env_prefix="GATEWAY_", case_sensitive=False)

    tender_upstream: str = Field(
        default="http://llama-tender:8080",
        description="Base URL (without trailing slash) for the tender LLM upstream.",
    )
    opencode_upstream: str = Field(
        default="http://llama-opencode:8080",
        description="Base URL (without trailing slash) for the opencode LLM upstream.",
    )
    tender_dmz_upstream: str | None = Field(
        default=None,
        description="Optional DMZ fallback for tender route.",
    )
    opencode_dmz_upstream: str | None = Field(
        default=None,
        description="Optional DMZ fallback for opencode route.",
    )
    anonymizer_url: str | None = Field(
        default=None,
        description="Optional anonymizer HTTP endpoint to relay external calls. If set, DMZ/externals are sent here with X-Target-Url header.",
    )
    tender_cloud_provider: str | None = Field(
        default=None,
        description="Optional external provider fallback for tender route. Supported: openai, anthropic.",
    )
    openai_base_url: str = Field(
        default="https://api.openai.com",
        description="Base URL for OpenAI API (OpenAI-compatible).",
    )
    openai_api_key: str | None = Field(
        default=None, description="API key used when tender_cloud_provider=openai."
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com",
        description="Base URL for Anthropic Claude API.",
    )
    anthropic_api_key: str | None = Field(
        default=None, description="API key used when tender_cloud_provider=anthropic."
    )
    gateway_timeout: float = Field(
        default=30.0, description="HTTP client timeout in seconds for upstream calls."
    )


def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Drop hop-by-hop headers that should not be forwarded."""
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
    return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}


async def _proxy_request(
    path: str,
    request: Request,
    timeout: float,
    candidates: list[dict],
) -> Response:
    """Forward the request across a list of candidate targets with fallback logic."""
    body = await request.body()
    headers = _safe_headers(dict(request.headers))

    last_response: httpx.Response | None = None

    for idx, candidate in enumerate(candidates):
        base = candidate["base"]
        via_anonymizer = bool(candidate.get("via_anonymizer"))
        anonymizer_url = candidate.get("anonymizer_url")
        api_key = candidate.get("api_key")
        provider = (candidate.get("provider") or "llama").lower()
        timeout_sec = float(candidate.get("timeout_sec") or timeout)
        max_attempts = int(candidate.get("max_attempts") or 2)

        target_path = path
        if path == "/completion" and provider in {"openai", "anthropic"}:
            target_path = "/v1/completions"

        # Build target URL and headers
        target_url = base.rstrip("/") + target_path
        outbound_headers = dict(headers)
        if api_key:
            outbound_headers["authorization"] = f"Bearer {api_key}"

        url_to_call = target_url
        if via_anonymizer and anonymizer_url:
            url_to_call = anonymizer_url.rstrip("/") + "/" + target_path.lstrip("/")
            outbound_headers["x-target-url"] = target_url

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    resp = await client.request(
                        request.method,
                        url_to_call,
                        content=body,
                        params=request.query_params,
                        headers=outbound_headers,
                    )

                last_response = resp

                if resp.status_code in {502, 503, 504}:
                    # Retry same target before falling back to next candidate
                    if attempt < max_attempts:
                        await asyncio.sleep(0.4 * attempt)
                        continue
                    break

                filtered_headers = {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower() in {"content-type", "content-length"}
                }
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=filtered_headers,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                # Retry same target before moving to next candidate
                if attempt < max_attempts:
                    await asyncio.sleep(0.4 * attempt)
                    continue
                break

        # try next candidate
        continue

    # If we reach here, all attempts failed
    status = last_response.status_code if last_response else 502
    content = (
        last_response.content if last_response else b"upstream unavailable"
    )
    return Response(content=content, status_code=status, media_type="text/plain")


import time

_cache = {}
_CACHE_TTL = 5.0

def _make_app(route_kind: str) -> FastAPI:
    """Factory to build a FastAPI app bound to a specific route."""
    settings = Settings()
    upstream = (
        settings.tender_upstream if route_kind == "tender" else settings.opencode_upstream
    )
    dmz_upstream = (
        settings.tender_dmz_upstream
        if route_kind == "tender"
        else settings.opencode_dmz_upstream
    )

    async def build_candidates() -> list[dict]:
        """Compose the ordered list of upstream targets for this route."""
        now = time.time()
        cands = []
        
        # Try fetching dynamic config from backend
        dynamic_targets_raw = None
        if route_kind in _cache:
            cached_time, cached_data = _cache[route_kind]
            if now - cached_time < _CACHE_TTL:
                dynamic_targets_raw = cached_data
                
        if dynamic_targets_raw is None:
            try:
                # 2 second timeout to not block the gateway for too long
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"http://tw-backend:8000/api/gateway/active-targets?route={route_kind}")
                    if resp.status_code == 200:
                        dynamic_targets_raw = resp.json()
                        _cache[route_kind] = (now, dynamic_targets_raw)
            except Exception:
                pass

        if dynamic_targets_raw:
            for t in dynamic_targets_raw:
                provider = (t.get("provider") or "").lower()
                api_key = None
                if provider == "openai":
                    api_key = settings.openai_api_key
                elif provider == "anthropic":
                    api_key = settings.anthropic_api_key
                    
                cands.append({
                    "base": t.get("base_url"),
                    "provider": (t.get("provider") or "llama").lower(),
                    "via_anonymizer": bool(t.get("use_anonymizer")) and settings.anonymizer_url is not None,
                    "anonymizer_url": settings.anonymizer_url,
                    "api_key": api_key,
                    "timeout_sec": max(5.0, float((t.get("timeout_ms") or 30000)) / 1000.0),
                    "max_attempts": 2,
                })
            if cands:
                return cands

        # Fallback to env variables if no dynamic targets
        cands = [
            {"base": upstream, "via_anonymizer": False, "anonymizer_url": None, "api_key": None, "provider": "llama", "timeout_sec": settings.gateway_timeout, "max_attempts": 2}
        ]
        if dmz_upstream:
            cands.append(
                {
                    "base": dmz_upstream,
                    "via_anonymizer": settings.anonymizer_url is not None,
                    "anonymizer_url": settings.anonymizer_url,
                    "api_key": None,
                    "timeout_sec": settings.gateway_timeout,
                    "max_attempts": 2,
                }
            )
        if route_kind == "tender":
            provider = (settings.tender_cloud_provider or "").lower()
            if provider == "openai" and settings.openai_api_key:
                cands.append(
                    {
                        "base": settings.openai_base_url,
                        "provider": "openai",
                        "via_anonymizer": settings.anonymizer_url is not None,
                        "anonymizer_url": settings.anonymizer_url,
                        "api_key": settings.openai_api_key,
                        "timeout_sec": settings.gateway_timeout,
                        "max_attempts": 2,
                    }
                )
            elif provider == "anthropic" and settings.anthropic_api_key:
                cands.append(
                    {
                        "base": settings.anthropic_base_url,
                        "provider": "anthropic",
                        "via_anonymizer": settings.anonymizer_url is not None,
                        "anonymizer_url": settings.anonymizer_url,
                        "api_key": settings.anthropic_api_key,
                        "timeout_sec": settings.gateway_timeout,
                        "max_attempts": 2,
                    }
                )
        return cands

    app = FastAPI(
        title=f"tw-gateway ({route_kind})",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/health")
    async def health():
        provider = settings.tender_cloud_provider if route_kind == "tender" else None
        cloud_base = None
        if route_kind == "tender":
            if (provider or "").lower() == "openai" and settings.openai_api_key:
                cloud_base = settings.openai_base_url
            elif (provider or "").lower() == "anthropic" and settings.anthropic_api_key:
                cloud_base = settings.anthropic_base_url
        cands = await build_candidates()
        
        return {
            "status": "ok",
            "route": route_kind,
            "upstream": upstream,
            "dmz_upstream": dmz_upstream,
            "anonymizer": settings.anonymizer_url,
            "cloud_provider": provider,
            "cloud_base": cloud_base,
            "dynamic_candidates": len(cands) if cands else 0,
        }

    @app.get("/v1/models")
    async def list_models(request: Request):
        return await _proxy_request(
            "/v1/models",
            request,
            settings.gateway_timeout,
            candidates=await build_candidates(),
        )

    @app.post("/completion")
    async def completion(request: Request):
        # llama.cpp completion endpoint (without /v1)
        return await _proxy_request(
            "/completion",
            request,
            settings.gateway_timeout,
            candidates=await build_candidates(),
        )

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        return await _proxy_request(
            "/v1/chat/completions",
            request,
            settings.gateway_timeout,
            candidates=await build_candidates(),
        )

    return app


def create_app_tender() -> FastAPI:
    """App factory for the tender route (port 8080)."""
    return _make_app("tender")


def create_app_opencode() -> FastAPI:
    """App factory for the opencode route (port 8081)."""
    return _make_app("opencode")
