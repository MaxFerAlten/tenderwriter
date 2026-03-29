import pytest
import httpx

from app.rag.generator import Generator


@pytest.mark.asyncio
async def test_generator_openrouter_uses_chat_completions(monkeypatch):
    seen = {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            seen["url"] = url
            seen["json"] = json
            seen["headers"] = headers
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "risposta openrouter",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 7,
                    },
                },
            )

    monkeypatch.setattr("app.rag.generator.httpx.AsyncClient", MockAsyncClient)

    generator = Generator(
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4.1-mini",
        provider="openrouter",
        api_key="sk-or-test",
        timeout=30,
    )

    result = await generator.generate(
        template="general_qa",
        variables={
            "context": "Contesto di test",
            "query": "Che cosa dice il documento?",
        },
    )

    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-or-test"
    assert seen["json"]["model"] == "openai/gpt-4.1-mini"
    assert seen["json"]["messages"][0]["content"]
    assert result.text == "risposta openrouter"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 7


@pytest.mark.asyncio
async def test_generator_explicit_chat_completions_url_stays_openai_compatible(monkeypatch):
    seen = {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            seen["url"] = url
            seen["json"] = json
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "risposta lm studio",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 21,
                        "completion_tokens": 11,
                    },
                },
            )

    monkeypatch.setattr("app.rag.generator.httpx.AsyncClient", MockAsyncClient)

    generator = Generator(
        base_url="http://127.0.0.1:1234/v1/chat/completions",
        model="qwen3.5-4b-claude-4.6-opus-reasoning-distilled",
        provider="llama",
        timeout=30,
    )

    result = await generator.generate(
        template="general_qa",
        variables={
            "context": "Contesto locale",
            "query": "Riassumi il problema di assegnamento",
        },
    )

    assert seen["url"].endswith("/v1/chat/completions")
    assert not seen["url"].endswith("/completion")
    assert seen["json"]["model"] == "qwen3.5-4b-claude-4.6-opus-reasoning-distilled"
    assert seen["json"]["messages"][0]["content"]
    assert result.text == "risposta lm studio"


def test_generator_rewrites_loopback_base_url_in_docker(monkeypatch):
    monkeypatch.setattr(Generator, "_running_in_docker", staticmethod(lambda: True))

    generator = Generator(
        base_url="http://127.0.0.1:1234/v1/chat/completions",
        model="qwen3.5-4b-claude-4.6-opus-reasoning-distilled",
        provider="llama",
        timeout=30,
    )

    assert generator.base_url == "http://host.docker.internal:1234/v1/chat/completions"
