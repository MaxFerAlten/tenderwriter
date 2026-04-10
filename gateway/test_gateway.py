import os
import json
import asyncio
import httpx
import importlib
import pytest
from starlette.requests import Request
from httpx import Response


async def _collect_streaming_body(response) -> str:
    chunks: list[str] = []
    async for item in response.body_iterator:
        if isinstance(item, bytes):
            chunks.append(item.decode("utf-8"))
        else:
            chunks.append(str(item))
    return "".join(chunks)


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


@pytest.mark.asyncio
async def test_openrouter_completion_translation(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Scrivi una risposta breve.",
                    "n_predict": 128,
                    "temperature": 0.2,
                    "stop": ["</s>"],
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "https://openrouter.ai/api/v1",
                "provider": "openrouter",
                "model_name": "openai/gpt-4.1-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": "sk-or-test",
                "timeout_sec": 30,
                "max_attempts": 1,
            }
        ],
    )

    assert resp.status_code == 200
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-or-test"
    assert seen["body"]["model"] == "openai/gpt-4.1-mini"
    assert seen["body"]["messages"][0]["content"] == "Scrivi una risposta breve."
    assert seen["body"]["max_tokens"] == 128


@pytest.mark.asyncio
async def test_openrouter_completion_drops_host_header(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        seen["host"] = request.headers.get("host")
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [
            (b"host", b"tw-gateway:8080"),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Scrivi una risposta breve.",
                    "n_predict": 64,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "https://openrouter.ai/api/v1",
                "provider": "openrouter",
                "model_name": "openai/gpt-4.1-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": "sk-or-test",
                "timeout_sec": 30,
                "max_attempts": 1,
            }
        ],
    )

    assert resp.status_code == 200
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["host"] == "openrouter.ai"
    assert seen["host"] != "tw-gateway:8080"
    assert seen["authorization"] == "Bearer sk-or-test"
    assert seen["body"]["model"] == "openai/gpt-4.1-mini"


@pytest.mark.asyncio
async def test_openrouter_falls_through_to_next_candidate(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = []

    def handler(request: httpx.Request) -> Response:
        seen.append(str(request.url))
        if "bad-target" in str(request.url):
            return Response(401, json={"detail": "unauthorized"})
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "fallback openrouter",
                    "n_predict": 64,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "https://bad-target.openrouter.ai/api/v1",
                "provider": "openrouter",
                "model_name": "openai/gpt-4.1-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": "sk-bad",
                "timeout_sec": 30,
                "max_attempts": 1,
            },
            {
                "base": "https://openrouter.ai/api/v1",
                "provider": "openrouter",
                "model_name": "openai/gpt-4.1-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": "sk-good",
                "timeout_sec": 30,
                "max_attempts": 1,
            },
        ],
    )

    assert resp.status_code == 200
    assert seen[0] == "https://bad-target.openrouter.ai/api/v1/chat/completions"
    assert seen[1] == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_llama_explicit_chat_endpoint_uses_openai_compatible_payload(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Riassumi in 100 parole.",
                    "n_predict": 96,
                    "temperature": 0.1,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "http://127.0.0.1:1234/v1/chat/completions",
                "provider": "llama",
                "model_name": "qwen3.5-4b-claude-4.6-opus-reasoning-distilled",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            }
        ],
    )

    assert resp.status_code == 200
    assert seen["url"].endswith("/v1/chat/completions")
    assert not seen["url"].endswith("/completion")
    assert seen["body"]["model"] == "qwen3.5-4b-claude-4.6-opus-reasoning-distilled"
    assert seen["body"]["messages"][0]["content"] == "Riassumi in 100 parole."


@pytest.mark.asyncio
async def test_gpt4free_upstream_can_be_configured_through_gateway_env(monkeypatch):
    os.environ["GATEWAY_TENDER_UPSTREAM"] = "http://gpt4free:8080/v1"
    os.environ["GATEWAY_TENDER_DMZ_UPSTREAM"] = "http://gpt4free:8080/v1"

    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)
    settings = gateway_app.Settings()
    assert settings.tender_upstream == "http://gpt4free:8080/v1"
    assert settings.tender_dmz_upstream == "http://gpt4free:8080/v1"

    seen = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Estrai i requisiti di partecipazione.",
                    "n_predict": 64,
                    "temperature": 0.1,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": settings.tender_upstream,
                "provider": "llama",
                "model_name": "gpt-4o-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            }
        ],
    )

    assert resp.status_code == 200
    assert seen["url"] == "http://gpt4free:8080/v1/chat/completions"
    assert seen["body"]["model"] == "gpt-4o-mini"
    assert seen["body"]["messages"][0]["content"] == "Estrai i requisiti di partecipazione."


@pytest.mark.asyncio
async def test_gpt4free_upstream_can_omit_model_name_and_use_provider_default(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "ok",
                        }
                    }
                ]
            },
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Riassumi il bando.",
                    "n_predict": 64,
                    "temperature": 0.1,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "http://gpt4free:8080/v1",
                "provider": "llama",
                "model_name": "",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            }
        ],
    )

    assert resp.status_code == 200
    assert seen["url"] == "http://gpt4free:8080/v1/chat/completions"
    assert "model" not in seen["body"]
    assert seen["body"]["messages"][0]["content"] == "Riassumi il bando."


@pytest.mark.asyncio
async def test_gpt4free_401_falls_through_to_llama_fallback(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = []

    def handler(request: httpx.Request) -> Response:
        seen.append(str(request.url))
        if "gpt4free" in str(request.url):
            return Response(401, json={"error": {"message": "Authentication failed"}})
        return Response(200, json={"content": "ok"})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Rispondi solo OK.",
                    "n_predict": 64,
                    "temperature": 0.1,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "http://gpt4free:8080/v1",
                "provider": "llama",
                "model_name": "gpt-4o-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            },
            {
                "base": "http://llama-tender:8080",
                "provider": "llama",
                "model_name": "gemma-3n-E4B-it-Q4_K_M.gguf",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            },
        ],
    )

    assert resp.status_code == 200
    assert json.loads(resp.body) == {"content": "ok"}
    assert seen[0] == "http://gpt4free:8080/v1/chat/completions"
    assert seen[1] == "http://llama-tender:8080/completion"


@pytest.mark.asyncio
async def test_gpt4free_stream_error_frame_falls_through_to_llama_fallback(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    seen = []

    def handler(request: httpx.Request) -> Response:
        seen.append(str(request.url))
        if "gpt4free" in str(request.url):
            return Response(
                200,
                content=b'data: {"error":{"message":"Authentication failed"},"model":"gpt-4o-mini"}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return Response(
            200,
            content=b'data: {"content":"OK"}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/completion",
        "headers": [],
        "query_string": b"",
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(
                {
                    "prompt": "Rispondi solo OK.",
                    "n_predict": 64,
                    "temperature": 0.1,
                    "stream": True,
                }
            ).encode("utf-8"),
            "more_body": False,
        }

    request = Request(scope, receive)
    resp = await gateway_app._proxy_request(
        path="/completion",
        request=request,
        timeout=30,
        candidates=[
            {
                "base": "http://gpt4free:8080/v1",
                "provider": "llama",
                "model_name": "gpt-4o-mini",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            },
            {
                "base": "http://llama-tender:8080",
                "provider": "llama",
                "model_name": "gemma-3n-E4B-it-Q4_K_M.gguf",
                "via_anonymizer": False,
                "anonymizer_url": None,
                "api_key": None,
                "timeout_sec": 30,
                "max_attempts": 1,
            },
        ],
    )

    assert resp.status_code == 200
    body = await _collect_streaming_body(resp)
    assert body == 'data: {"content":"OK"}\n\ndata: [DONE]\n\n'
    assert seen[0] == "http://gpt4free:8080/v1/chat/completions"
    assert seen[1] == "http://llama-tender:8080/completion"


@pytest.mark.asyncio
async def test_dynamic_target_cache_coalesces_concurrent_backend_fetches(monkeypatch):
    import gateway.app as gateway_app
    gateway_app = importlib.reload(gateway_app)

    app = gateway_app.create_app_tender()
    health_endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/health")

    release = asyncio.Event()
    backend_fetches = 0

    class _FakeDynamicResponse:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "base_url": "http://dynamic-target",
                    "provider": "llama",
                    "model_name": "dynamic-model",
                    "use_anonymizer": False,
                    "timeout_ms": 30000,
                }
            ]

    class PatchedAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            nonlocal backend_fetches
            backend_fetches += 1
            if backend_fetches == 1:
                asyncio.get_running_loop().call_later(0.05, release.set)
            await release.wait()
            return _FakeDynamicResponse()

    monkeypatch.setattr(gateway_app.httpx, "AsyncClient", PatchedAsyncClient)

    responses = await asyncio.gather(*(health_endpoint() for _ in range(5)))

    assert backend_fetches == 1
    assert all(response["dynamic_candidates"] == 1 for response in responses)
