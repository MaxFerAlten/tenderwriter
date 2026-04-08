"""XAI Grok provider — Grok-2, Grok-3, etc.

Uses the OpenAI-compatible API that xAI exposes.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.config import settings
from backend.schemas.messages import TokenUsage
from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError

logger = logging.getLogger("tenderclaw.providers.xai")

XAI_BASE_URL = "https://api.x.ai/v1"


class XAIProvider(BaseProvider):
    """Provider for xAI Grok models (OpenAI-compatible API)."""

    name = "xai"
    models = ["grok"]

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.xai_api_key
        if not key:
            raise ProviderError("XAI_API_KEY not set")
        self._client = AsyncOpenAI(api_key=key, base_url=XAI_BASE_URL)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion from xAI Grok API."""
        oai_messages: list[dict[str, Any]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            oai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=oai_messages,
                max_tokens=max_tokens,
                stream=True,
            )

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
                        "delta": {"stop_reason": "end_turn"},
                    }

            yield {"type": "usage", "usage": TokenUsage()}

        except Exception as exc:
            logger.error("xAI API error: %s", exc)
            raise ProviderError(f"xAI API error: {exc}") from exc
