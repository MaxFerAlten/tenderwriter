"""LM Studio provider — local models via LM Studio.

Uses the OpenAI-compatible API that LM Studio exposes at localhost:1234.
"""

from __future__ import annotations

import logging
import urllib.request as _urlreq
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.config import settings
from backend.schemas.messages import TokenUsage
from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError

logger = logging.getLogger("tenderclaw.providers.lmstudio")


class LMStudioProvider(BaseProvider):
    """Provider for local LM Studio models."""

    name = "lmstudio"
    models = ["lmstudio"]

    def __init__(self, base_url: str | None = None) -> None:
        url = base_url or settings.lmstudio_base_url
        if not url.endswith("/v1"):
            url = url.rstrip("/") + "/v1"
        self._base_url = url
        self._healthy = False
        try:
            probe = self._base_url.rstrip("/") + "/models"
            with _urlreq.urlopen(probe, timeout=2) as resp:
                if resp.status == 200:
                    self._healthy = True
        except Exception:
            self._healthy = False
        self._client = AsyncOpenAI(api_key="lm-studio", base_url=self._base_url)
        logger.info("LM Studio provider initialized with base_url: %s", self._base_url)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion from LM Studio."""
        oai_messages: list[dict[str, Any]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            oai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        if not getattr(self, "_healthy", True):
            raise ProviderError(f"LM Studio not healthy or not reachable at {self._base_url}")

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
                # LM Studio may return empty content but use reasoning_content
                content = delta.content if delta else ""
                reasoning = getattr(delta, "reasoning_content", None) if delta else None
                
                if content:
                    yield {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": content},
                    }
                elif reasoning:
                    yield {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": reasoning},
                    }
                if choice.finish_reason:
                    yield {
                        "type": "message_delta",
                        "delta": {"stop_reason": choice.finish_reason},
                    }

            yield {"type": "usage", "usage": TokenUsage()}

        except Exception as exc:
            logger.error("LM Studio error: %s", exc)
            raise ProviderError(
                f"LM Studio error: {exc}. Is LM Studio running at {settings.lmstudio_base_url}?"
            ) from exc
