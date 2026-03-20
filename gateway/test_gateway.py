import os
import json
import httpx
import importlib
import pytest
from starlette.requests import Request
from httpx import Response


@pytest.mark.asyncio
async def test_fallback_to_dmz_without_anonymizer(monkeypatch):
    os.environ["GATEWAY_TENDER_UPSTREAM"] = "http://primary"
    os.environ["GATEWAY_TENDER_DMZ_UPSTREAM"] = "http://dmz"
    os.environ.pop("GATEWAY_ANONYMIZER_URL", None)

    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)
    settings = gateway_app.Settings()
    assert settings.tender_upstream == "http://primary"
    assert settings.tender_dmz_upstream == "http://dmz"

    def handler(request: httpx.Request) -> Response:
        if "primary" in request.url.host:
            return Response(503)
        if "dmz" in request.url.host:
            return Response(200, json={"ok": True})
        return Response(500)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/models",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/v1/models",
        request=request,
        timeout=settings.gateway_timeout,
        candidates=[
            {
                "base": settings.tender_upstream,
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
            },
            {
                "base": settings.tender_dmz_upstream,
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
            },
        ],
    )

    assert resp.status_code == 200, repr(resp.body)
    assert json.loads(resp.body) == {"ok": True}


@pytest.mark.asyncio
async def test_fallback_uses_anonymizer(monkeypatch):
    os.environ["GATEWAY_TENDER_UPSTREAM"] = "http://primary"
    os.environ["GATEWAY_TENDER_DMZ_UPSTREAM"] = "http://dmz"
    os.environ["GATEWAY_ANONYMIZER_URL"] = "http://anonymizer:8090"

    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)
    settings = gateway_app.Settings()
    assert settings.tender_upstream == "http://primary"
    assert settings.tender_dmz_upstream == "http://dmz"
    assert settings.anonymizer_url == "http://anonymizer:8090"

    seen = {}

    def handler(request: httpx.Request) -> Response:
        if "primary" in request.url.host:
            return Response(503)
        if "anonymizer" in request.url.host:
            seen["target"] = request.headers.get("x-target-url")
            return Response(200, json={"via": "anonymizer"})
        return Response(500)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/models",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/v1/models",
        request=request,
        timeout=settings.gateway_timeout,
        candidates=[
            {
                "base": settings.tender_upstream,
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
            },
            {
                "base": settings.tender_dmz_upstream,
                "via_anonymizer": True,
                "anonymizer_url": settings.anonymizer_url,
                "api_key": None,
            },
        ],
    )

    assert resp.status_code == 200, repr(resp.body)
    assert json.loads(resp.body) == {"via": "anonymizer"}
    assert seen.get("target") == "http://dmz/v1/models"


@pytest.mark.asyncio
async def test_cloud_fallback_with_anonymizer_and_api_key(monkeypatch):
    os.environ["GATEWAY_TENDER_UPSTREAM"] = "http://primary"
    os.environ["GATEWAY_TENDER_DMZ_UPSTREAM"] = "http://dmz"
    os.environ["GATEWAY_ANONYMIZER_URL"] = "http://anonymizer:8090"
    os.environ["GATEWAY_TENDER_CLOUD_PROVIDER"] = "openai"
    os.environ["GATEWAY_OPENAI_BASE_URL"] = "https://api.openai.com"
    os.environ["GATEWAY_OPENAI_API_KEY"] = "sk-test"

    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)
    settings = gateway_app.Settings()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Response:
        calls.append(request)
        host = request.url.host
        if "primary" in host or "dmz" in host:
            return Response(503)
        if "anonymizer" in host:
            target = request.headers.get("x-target-url", "")
            if "dmz" in target:
                return Response(503)
            if "api.openai.com" in target:
                return Response(200, json={"provider": "openai"})
        return Response(500)

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": b'{"messages":[]}', "more_body": False}

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/v1/chat/completions",
        request=request,
        timeout=settings.gateway_timeout,
        candidates=[
            {
                "base": settings.tender_upstream,
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
            },
            {
                "base": settings.tender_dmz_upstream,
                "via_anonymizer": settings.anonymizer_url is not None,
                "anonymizer_url": settings.anonymizer_url,
                "api_key": None,
            },
            {
                "base": settings.openai_base_url,
                "via_anonymizer": settings.anonymizer_url is not None,
                "anonymizer_url": settings.anonymizer_url,
                "api_key": settings.openai_api_key,
            },
        ],
    )

    assert resp.status_code == 200
    assert json.loads(resp.body) == {"provider": "openai"}

    # Last call should target anonymizer with correct headers
    last = calls[-1]
    assert last.url.host == "anonymizer"
    assert last.headers.get("x-target-url") == "https://api.openai.com/v1/chat/completions"
    assert last.headers.get("authorization") == "Bearer sk-test"
