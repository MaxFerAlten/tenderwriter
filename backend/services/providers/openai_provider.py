"""OpenAI provider — GPT, o1, o3, GPT-5 models."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.config import settings
from backend.schemas.messages import TokenUsage
from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError

logger = logging.getLogger("tenderclaw.providers.openai")


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI models (GPT-4o, o1, o3, GPT-5, etc.)."""

    name = "openai"
    models = ["gpt", "o1", "o3", "chatgpt"]

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise ProviderError("OPENAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=key)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion from OpenAI, normalized to TenderClaw format."""
        oai_messages: list[dict[str, Any]] = []

        if system:
            oai_messages.append({"role": "system", "content": system})

        for msg in messages:
            oai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        oai_tools = _convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools

        try:
            stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                delta = choice.delta
                if delta and delta.content:
                    yield {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": delta.content},
                    }

                if choice.finish_reason:
                    yield {
                        "type": "message_delta",
                        "delta": {"stop_reason": _map_finish_reason(choice.finish_reason)},
                    }

            # Yield usage estimate
            yield {
                "type": "usage",
                "usage": TokenUsage(input_tokens=0, output_tokens=0),
            }

        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            raise ProviderError(f"OpenAI API error: {exc}") from exc


def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-format tools to OpenAI function-calling format."""
    oai_tools = []
    for tool in tools:
        oai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return oai_tools


def _map_finish_reason(reason: str) -> str:
    """Map OpenAI finish reasons to Anthropic-compatible ones."""
    mapping = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "content_filter": "end_turn",
    }
    return mapping.get(reason, "end_turn")
