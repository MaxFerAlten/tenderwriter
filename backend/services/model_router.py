"""Model router — route requests to the correct AI provider.

Multi-model from day 1: Claude, GPT, Gemini, Grok, DeepSeek, Ollama.
Providers are lazy-initialized on first use to avoid startup failures
when API keys are missing for unused providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from backend.services.providers.base import BaseProvider
from backend.utils.errors import ProviderError


@dataclass
class GenerateResult:
    """Non-streaming response collected from a provider stream."""
    content: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

logger = logging.getLogger("tenderclaw.services.model_router")

# Model name prefix -> provider name
PROVIDER_MAP: dict[str, str] = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "chatgpt": "openai",
    "gemini": "google",
    "grok": "xai",
    "deepseek": "deepseek",
    "lmstudio": "lmstudio",
    "lm-studio": "lmstudio",
    "mistral": "ollama",
    "codellama": "ollama",
    "phi": "ollama",
    "qwen": "ollama",
    "gemma": "ollama",
    "llama": "ollama",
}


def detect_provider(model: str) -> str:
    """Detect the provider from a model name."""
    model_lower = model.lower()
    # LM Studio uses namespaced models like "qwen/qwen3.5-9b"
    if "/" in model:
        return "lmstudio"
    for prefix, provider in PROVIDER_MAP.items():
        if prefix in model_lower:
            return provider
    return "anthropic"


class ModelRouter:
    """Routes model requests to the correct provider client."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def _get_provider(self, name: str, config: dict[str, Any] | None = None) -> BaseProvider:
        """Lazy-init a provider by name."""
        # For Ollama/LM Studio, always recreate to use new URL
        if name in ("ollama", "lmstudio"):
            provider = _create_provider(name, config)
            self._providers[name] = provider
            return provider
        
        if name in self._providers:
            return self._providers[name]

        provider = _create_provider(name, config)
        self._providers[name] = provider
        logger.info("Provider initialized: %s", name)
        return provider

    async def stream_message(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Route a streaming message request to the appropriate provider."""
        provider_name = detect_provider(model)
        provider = self._get_provider(provider_name, config)

        try:
            async for event in provider.stream(
            model=model,
            messages=messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            ):
                yield event
        except ProviderError as exc:
            # Fallback to a cloud provider only when explicitly allowed via config
            if provider_name in ("ollama", "lmstudio"):
                from backend.config import settings
                # Only fall back if no_fallback flag is absent in config
                no_fallback = config.get("no_fallback", False) if config else False
                if not no_fallback:
                    fallback_name = None
                    if settings.anthropic_api_key:
                        fallback_name = "anthropic"
                    elif settings.openai_api_key:
                        fallback_name = "openai"
                    if fallback_name:
                        logger.warning(
                            "%s unreachable (%s); falling back to %s. "
                            "Pass no_fallback=true in config to disable this.",
                            provider_name, exc, fallback_name,
                        )
                        try:
                            fallback = self._get_provider(fallback_name)
                            async for event in fallback.stream(
                                model=model,
                                messages=messages,
                                system=system,
                                tools=tools,
                                max_tokens=max_tokens,
                            ):
                                yield event
                            return
                        except Exception as inner:
                            logger.error("Fallback provider %s failed: %s", fallback_name, inner)
                            raise
            raise

    async def generate_message(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> GenerateResult:
        """Non-streaming convenience: collect full response as a single string."""
        parts: list[str] = []
        usage_info: dict[str, Any] = {}

        async for event in self.stream_message(
            model=model,
            messages=messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
        ):
            evt_type = event.get("type", "")
            if evt_type == "content_block_delta":
                text = event.get("delta", {}).get("text", "")
                if text:
                    parts.append(text)
            elif evt_type == "message_delta" and "usage" in event:
                usage_info = event["usage"]

        return GenerateResult(content="".join(parts), usage=usage_info)

    def list_providers(self) -> list[str]:
        """List all available provider names."""
        return list(PROVIDER_MAP.values())


def _create_provider(name: str, config: dict[str, Any] | None = None) -> BaseProvider:
    """Factory function — create a provider instance by name."""
    if name == "anthropic":
        from backend.services.anthropic_client import AnthropicClient
        return AnthropicClient()
    if name == "openai":
        from backend.services.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "google":
        from backend.services.providers.google_provider import GoogleProvider
        return GoogleProvider()
    if name == "deepseek":
        from backend.services.providers.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider()
    if name == "xai":
        from backend.services.providers.xai_provider import XAIProvider
        return XAIProvider()
    if name == "ollama":
        from backend.services.providers.ollama_provider import OllamaProvider
        url = config.get("ollama_url") if config else None
        return OllamaProvider(base_url=url)
    if name == "lmstudio":
        from backend.services.providers.lmstudio_provider import LMStudioProvider
        url = config.get("lmstudio_url") if config else None
        return LMStudioProvider(base_url=url)

    raise ProviderError(f"Unknown provider: {name}")


# Module-level instance
model_router = ModelRouter()
