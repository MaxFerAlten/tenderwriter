"""Wisdom Accumulator — store and retrieve successful coding patterns.

Wisdom items are extracted from successful task completions to
inform the agent in future sessions. Supports pattern learning
and usage-based retrieval.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("tenderclaw.memory.wisdom")


class WisdomItem(BaseModel):
    """A single piece of accumulated knowledge."""

    id: str
    task_type: str
    description: str
    solution_pattern: str
    success_score: float = 1.0
    created_at: datetime = Field(default_factory=datetime.now)
    last_used_at: datetime = Field(default_factory=datetime.now)
    usage_count: int = 0
    tags: list[str] = Field(default_factory=list)
    code_snippet: str | None = None


class WisdomStore:
    """Persistent storage for accumulated wisdom with smart retrieval."""

    def __init__(self, storage_path: str = ".tenderclaw/wisdom") -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._wisdom: list[WisdomItem] = []
        self._load_all()

    def add(self, item: WisdomItem) -> None:
        """Store a new piece of wisdom."""
        self._wisdom.append(item)
        self._save(item)
        self._extract_and_tag(item)
        logger.info("New wisdom added: %s (%s)", item.description[:50], item.id)

    def find_relevant(self, query: str, limit: int = 5) -> list[WisdomItem]:
        """Find wisdom items relevant to a task query with scoring."""
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        
        scored: list[tuple[float, WisdomItem]] = []
        
        for item in self._wisdom:
            score = 0.0
            
            # Exact task_type match
            if query_lower in item.task_type.lower():
                score += 3.0
            
            # Keyword matches in description
            desc_words = set(re.findall(r'\w+', item.description.lower()))
            matches = query_words & desc_words
            score += len(matches) * 0.5
            
            # Tag matches
            for tag in item.tags:
                if tag.lower() in query_lower:
                    score += 1.0
            
            # Recency boost (recent items score higher)
            days_old = (datetime.now() - item.last_used_at).days
            score += max(0, 1.0 - days_old / 30)
            
            # Usage boost (frequently used items)
            score += min(item.usage_count * 0.1, 2.0)
            
            # Success score weight
            score *= item.success_score
            
            if score > 0:
                scored.append((score, item))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def find_relevant_contextual(
        self,
        messages: list[dict[str, object]],
        limit: int = 5,
    ) -> list["WisdomItem"]:
        """Find wisdom relevant to a multi-turn conversation context.

        Builds a composite keyword query from the last few messages, then
        delegates to find_relevant for scoring.
        """
        from backend.memory.keyword_extractor import extract_keywords

        texts: list[str] = []
        for msg in messages[-4:]:
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))

        composite = " ".join(texts)
        if not composite.strip():
            return []

        keywords = extract_keywords(composite, top_n=12)
        query = " ".join(keywords)
        return self.find_relevant(query, limit=limit)

    def format_for_prompt(self, items: list["WisdomItem"]) -> str:
        """Format wisdom items as a compact markdown block for prompt injection."""
        if not items:
            return ""
        lines = ["## Relevant Past Patterns"]
        for item in items:
            tag_str = ", ".join(item.tags[:3]) if item.tags else ""
            line = f"- [{item.task_type}] {item.description}: {item.solution_pattern}"
            if tag_str:
                line += f" (tags: {tag_str})"
            lines.append(line)
        return "\n".join(lines)

    def record_usage(self, wisdom_id: str) -> None:
        """Record that a wisdom item was used."""
        for item in self._wisdom:
            if item.id == wisdom_id:
                item.usage_count += 1
                item.last_used_at = datetime.now()
                self._save(item)
                break

    def get_stats(self) -> dict[str, Any]:
        """Get wisdom store statistics."""
        return {
            "total_items": len(self._wisdom),
            "by_type": self._count_by_field("task_type"),
            "by_tag": self._count_by_field("tags"),
            "avg_success_score": sum(w.success_score for w in self._wisdom) / len(self._wisdom) if self._wisdom else 0,
            "most_used": sorted(self._wisdom, key=lambda w: w.usage_count, reverse=True)[:5],
        }

    def suggest_tags(self, text: str) -> list[str]:
        """Suggest tags based on text content."""
        suggestions = []
        
        # Tech stack patterns
        tech_patterns = {
            "react": [r"react", r"jsx", r"tsx", r"hooks?"],
            "python": [r"python", r"pip", r"pydantic", r"fastapi"],
            "typescript": [r"typescript", r"ts", r"interface", r"type \w+"],
            "database": [r"sql", r"postgres", r"mongodb", r"sqlite"],
            "api": [r"api", r"rest", r"endpoint", r"router"],
            "testing": [r"test", r"pytest", r"jest", r"coverage"],
            "security": [r"auth", r"security", r"jwt", r"oauth"],
            "devops": [r"docker", r"ci/cd", r"deploy", r"kubernetes"],
        }
        
        for tag, patterns in tech_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    if tag not in suggestions:
                        suggestions.append(tag)
                    break
        
        return suggestions[:5]

    def _count_by_field(self, field: str) -> dict[str, int]:
        """Count items by a specific field value."""
        counts: dict[str, int] = {}
        for item in self._wisdom:
            if field == "task_type":
                key = item.task_type
                counts[key] = counts.get(key, 0) + 1
            elif field == "tags":
                for tag in item.tags:
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    def _extract_and_tag(self, item: WisdomItem) -> None:
        """Extract tags from wisdom item content."""
        text = f"{item.description} {item.solution_pattern}"
        item.tags = self.suggest_tags(text)
        self._save(item)

    def _save(self, item: WisdomItem) -> None:
        """Save item to disk."""
        file_path = self.storage_path / f"{item.id}.json"
        file_path.write_text(item.model_dump_json(indent=2), encoding="utf-8")

    def _load_all(self) -> None:
        """Load all wisdom files from disk."""
        for file_path in self.storage_path.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                self._wisdom.append(WisdomItem.model_validate(data))
            except Exception as exc:
                logger.error("Failed to load wisdom %s: %s", file_path, exc)


# Module-level instance
wisdom_store = WisdomStore()
