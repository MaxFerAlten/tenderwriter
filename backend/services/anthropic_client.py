"""Anthropic API client — async streaming wrapper for Claude models."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import anthropic

from backend.config import settings
from backend.schemas.messages import Message, TokenUsage
from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError

logger = logging.getLogger("tenderclaw.services.anthropic")


class AnthropicClient(BaseProvider):
    """Async client for the Anthropic Messages API with streaming."""

    name = "anthropic"
    models = ["claude"]

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.AsyncAnthropic(api_key=key)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a message from the Anthropic API.

        Yields event dicts with 'type' key:
          - content_block_start
          - content_block_delta
          - content_block_stop
          - message_start
          - message_delta
          - message_stop
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    yield self._normalize_event(event)

                # Yield final usage
                final = await stream.get_final_message()
                yield {
                    "type": "usage",
                    "usage": TokenUsage(
                        input_tokens=final.usage.input_tokens,
                        output_tokens=final.usage.output_tokens,
                    ),
                }

        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            raise ProviderError(f"Anthropic API error: {exc}") from exc

    def _normalize_event(self, event: Any) -> dict[str, Any]:
        """Convert Anthropic SDK event to a plain dict."""
        event_dict: dict[str, Any] = {"type": event.type}

        if event.type == "content_block_start":
            block = event.content_block
            event_dict["index"] = event.index
            event_dict["content_block"] = {
                "type": block.type,
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "text": getattr(block, "text", ""),
            }

        elif event.type == "content_block_delta":
            delta = event.delta
            event_dict["index"] = event.index
            event_dict["delta"] = {
                "type": delta.type,
                "text": getattr(delta, "text", ""),
                "partial_json": getattr(delta, "partial_json", ""),
                "thinking": getattr(delta, "thinking", ""),
            }

        elif event.type == "content_block_stop":
            event_dict["index"] = event.index

        elif event.type == "message_delta":
            event_dict["delta"] = {
                "stop_reason": getattr(event.delta, "stop_reason", None),
            }
            if hasattr(event, "usage"):
                event_dict["usage"] = {
                    "output_tokens": event.usage.output_tokens,
                }

        return event_dict
