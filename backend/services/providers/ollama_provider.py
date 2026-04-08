"""Ollama provider — local models (Llama, Qwen, Mistral, CodeLlama, etc.).

Uses the OpenAI-compatible API that Ollama exposes at localhost:11434.
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

logger = logging.getLogger("tenderclaw.providers.ollama")


class OllamaProvider(BaseProvider):
    """Provider for local Ollama models."""

    name = "ollama"
    models = ["llama", "qwen", "mistral", "codellama", "deepseek-coder", "phi", "gemma", "mixtral", "deepseek"]

    def __init__(self, base_url: str | None = None) -> None:
        # Ollama uses OpenAI-compatible API at /v1/chat/completions
        url = base_url or settings.ollama_base_url
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
        self._client = AsyncOpenAI(api_key="ollama", base_url=self._base_url)
        logger.info("Ollama provider initialized with base_url: %s", self._base_url)

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion from local Ollama instance."""
        oai_messages: list[dict[str, Any]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for msg in messages:
            oai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        if not getattr(self, "_healthy", True):
            raise ProviderError(f"Ollama not healthy or not reachable at {self._base_url}")

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
            logger.error("Ollama error: %s", exc)
            raise ProviderError(
                f"Ollama error: {exc}. Is Ollama running at {settings.ollama_base_url}?"
            ) from exc
