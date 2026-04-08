"""Google Gemini provider — Gemini 2.5 Pro, Flash, etc."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from backend.config import settings
from backend.schemas.messages import TokenUsage
from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError

logger = logging.getLogger("tenderclaw.providers.google")


class GoogleProvider(BaseProvider):
    """Provider for Google Gemini models."""

    name = "google"
    models = ["gemini"]

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.google_api_key
        if not key:
            raise ProviderError("GOOGLE_API_KEY not set")
        self._api_key = key

    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream completion from Google Gemini API."""
        from google import genai

        client = genai.Client(api_key=self._api_key)

        # Convert messages to Gemini format
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "model" if msg.get("role") == "assistant" else "user"
            content = msg.get("content", "")
            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})

        config = {"max_output_tokens": max_tokens}
        if system:
            config["system_instruction"] = system

        try:
            response = client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )

            for chunk in response:
                if chunk.text:
                    yield {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": chunk.text},
                    }

            yield {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
            }
            yield {
                "type": "usage",
                "usage": TokenUsage(input_tokens=0, output_tokens=0),
            }

        except Exception as exc:
            logger.error("Google API error: %s", exc)
            raise ProviderError(f"Google API error: {exc}") from exc
