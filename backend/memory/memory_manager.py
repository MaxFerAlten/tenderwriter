"""Memory Manager — orchestrates wisdom retrieval for conversation injection.

Usage in conversation.py:
    from backend.memory.memory_manager import memory_manager
    wisdom_context = memory_manager.get_relevant_context(api_messages, limit=5)
"""

from __future__ import annotations

import logging
from typing import Any

from backend.memory.keyword_extractor import extract_keywords

logger = logging.getLogger("tenderclaw.memory.memory_manager")

# Number of recent messages to include in keyword extraction
_CONTEXT_WINDOW = 4


class MemoryManager:
    """Retrieves and formats relevant wisdom for injection into the system prompt."""

    def get_relevant_context(
        self,
        messages: list[dict[str, Any]],
        limit: int = 5,
    ) -> str:
        """Build a formatted wisdom block from messages relevant to the conversation.

        Returns an empty string if no relevant wisdom is found or the store is empty.
        """
        try:
            from backend.memory.wisdom import wisdom_store
        except ImportError:
            return ""

        if not messages:
            return ""

        # Extract text from the most recent messages (weighted toward recent)
        window = messages[-_CONTEXT_WINDOW:]
        texts: list[str] = []
        for i, msg in enumerate(window):
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))

        composite = " ".join(texts)
        if not composite.strip():
            return ""

        keywords = extract_keywords(composite, top_n=12)
        if not keywords:
            return ""

        query = " ".join(keywords)
        try:
            items = wisdom_store.find_relevant(query, limit=limit)
        except Exception as exc:
            logger.warning("Wisdom retrieval failed: %s", exc)
            return ""

        if not items:
            return ""

        return _format_for_prompt(items)


def _format_for_prompt(items: list[Any]) -> str:
    """Serialize wisdom items into a compact markdown block."""
    lines = ["## Relevant Past Patterns"]
    for item in items:
        tag_str = (", ".join(item.tags[:3]) if item.tags else "")
        line = f"- [{item.task_type}] {item.description}: {item.solution_pattern}"
        if tag_str:
            line += f" (tags: {tag_str})"
        lines.append(line)
    return "\n".join(lines)


# Module-level singleton
memory_manager = MemoryManager()
