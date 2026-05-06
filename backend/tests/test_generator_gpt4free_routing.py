"""Routing tests for GPT4Free OpenAI-compatible endpoints."""

from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

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

from app.rag.generator import GenerationResult, Generator


class GeneratorGPT4FreeRoutingTests(unittest.TestCase):
    def test_generator_treats_gpt4free_v1_endpoint_as_openai_compatible_chat_api(self) -> None:
        generator = Generator(
            base_url="http://gpt4free:8080/v1",
            model="gpt-4o-mini",
        )

        self.assertTrue(generator._uses_openai_compatible_chat_api())
        self.assertEqual(generator._openai_compatible_root_url(), "http://gpt4free:8080/v1")
        self.assertEqual(
            generator._openai_chat_url(),
            "http://gpt4free:8080/v1/chat/completions",
        )

    def test_generator_auto_appends_v1_for_bare_gpt4free_base_url(self) -> None:
        generator = Generator(
            base_url="http://gpt4free:8080",
            model="gpt-4o-mini",
        )

        self.assertEqual(generator.base_url, "http://gpt4free:8080/v1")
        self.assertTrue(generator._uses_openai_compatible_chat_api())

    def test_extract_stream_error_message_reads_nested_provider_error_payloads(self) -> None:
        message = Generator._extract_stream_error_message(
            {
                "error": {
                    "message": "NoValidHarFileError: No .har file found",
                },
                "model": "gpt-4o-mini",
            }
        )

        self.assertEqual(message, "NoValidHarFileError: No .har file found")

    def test_raise_for_stream_error_chunk_ignores_regular_token_payloads(self) -> None:
        Generator._raise_for_stream_error_chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "content": "ciao",
                        }
                    }
                ]
            },
            context="OpenAI-compatible chat streaming generation failed",
        )

    def test_should_retry_empty_openai_response_when_reasoning_field_is_present(self) -> None:
        should_retry = Generator._should_retry_empty_openai_response(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": "",
                            "reasoning": "Reasoning only",
                        },
                    }
                ]
            }
        )

        self.assertTrue(should_retry)

    def test_requested_token_timeout_uses_twenty_minute_floor(self) -> None:
        generator = Generator(
            base_url="http://tw-gateway:8080/v1",
            model="gpt-4o-mini",
            timeout=1200,
        )

        self.assertEqual(generator._timeout_for_requested_tokens(512), 1200)
        self.assertEqual(generator._timeout_for_requested_tokens(1536), 1200)

    def test_extended_retry_timeout_adds_ten_minutes(self) -> None:
        generator = Generator(
            base_url="http://tw-gateway:8080/v1",
            model="gpt-4o-mini",
            timeout=1200,
        )

        self.assertEqual(generator._expanded_retry_timeout(), 1800)


class GeneratorGatewayRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_json_extends_timeout_by_ten_minutes_while_llm_server_is_alive(self) -> None:
        generator = Generator(
            base_url="http://tw-gateway:8080/v1",
            model="gpt-4o-mini",
            timeout=1200,
        )
        generator._llm_server_alive_for_timeout_extension = AsyncMock(return_value=True)
        client_timeouts: list[float] = []
        post_attempts = 0

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"ok": True}

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                del args
                client_timeouts.append(kwargs.get("timeout"))

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, *args, **kwargs):
                del args, kwargs
                nonlocal post_attempts
                post_attempts += 1
                if post_attempts <= 2:
                    import httpx

                    raise httpx.TimeoutException("slow generation")
                return _FakeResponse()

        with patch("app.rag.generator.httpx.AsyncClient", _FakeAsyncClient):
            result = await generator._post_json_with_retries(
                url="http://tw-gateway:8080/v1/chat/completions",
                request_data={"messages": []},
                headers={},
                context="Llama server",
                timeout=1200,
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(client_timeouts, [1200, 1800, 2400])
        self.assertEqual(generator._llm_server_alive_for_timeout_extension.await_count, 2)

    async def test_gateway_backed_generate_retries_when_response_has_only_reasoning(self) -> None:
        generator = Generator(
            base_url="http://tw-gateway:8080/v1",
            model="gpt-4o-mini",
        )
        generator._post_json_with_retries = AsyncMock(
            side_effect=[
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": "",
                                "reasoning": "Reasoning only",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 256},
                },
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "Sintesi finale.",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 120},
                },
            ]
        )

        result = await generator.generate(
            template="Rispondi con una sintesi breve.",
            variables={},
            max_tokens=256,
        )

        self.assertEqual(result.text, "Sintesi finale.")
        self.assertEqual(generator._post_json_with_retries.await_count, 2)

    async def test_gateway_backed_stream_retries_after_reasoning_only_chunks(self) -> None:
        generator = Generator(
            base_url="http://tw-gateway:8080/v1",
            model="gpt-4o-mini",
        )

        class _FakeStreamResponse:
            def raise_for_status(self) -> None:
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def aiter_lines(self):
                lines = [
                    'data: {"choices":[{"delta":{"reasoning":"Thinking"},"finish_reason":null}]}',
                    'data: {"choices":[{"delta":{"content":""},"finish_reason":"length"}]}',
                    "data: [DONE]",
                ]
                for line in lines:
                    yield line

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            def stream(self, *args, **kwargs):
                return _FakeStreamResponse()

        generator.generate = AsyncMock(
            return_value=GenerationResult(
                text="Sintesi finale dopo retry.",
                model="gpt-4o-mini",
                template_used="custom",
            )
        )

        with patch("app.rag.generator.httpx.AsyncClient", _FakeAsyncClient):
            chunks = []
            async for token in generator.generate_stream(
                template="Rispondi con una sintesi breve.",
                variables={},
                max_tokens=256,
            ):
                chunks.append(token)

        self.assertEqual("".join(chunks), "Sintesi finale dopo retry.")
        generator.generate.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
