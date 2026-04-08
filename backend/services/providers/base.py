"""Base provider interface — every AI provider implements this.

Inspired by OpenClaw's plugin-based provider system but with a clean Python ABC.
"""

from __future__ import annotations

import abc
from typing import Any, AsyncIterator


class BaseProvider(abc.ABC):
    """Abstract base for all model providers."""

    name: str = ""
    models: list[str] = []

    @abc.abstractmethod
    async def stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a completion response.

        Yields normalized event dicts with a 'type' key.
        All providers must normalize to the same event format.
        """
        ...  # pragma: no cover

    def supports(self, model: str) -> bool:
        """Check if this provider supports the given model."""
        model_lower = model.lower()
        return any(m.lower() in model_lower for m in self.models)
