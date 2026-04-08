"""Memory Types — data models for the MEMORY.md system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Taxonomy of memory entries."""

    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


class MemoryMetadata(BaseModel):
    """Metadata for a memory entry."""

    source_file: str | None = None
    line_number: int | None = None
    tags: list[str] = Field(default_factory=list)
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    accessed_count: int = 0
    last_accessed: datetime | None = None
    confidence: float = 1.0


class MemoryEntry(BaseModel):
    """A single memory entry with taxonomy and relevance tracking."""

    id: str
    type: MemoryType
    title: str
    content: str
    keywords: list[str] = Field(default_factory=list)
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    relevance_score: float = 0.0

    def touch(self) -> None:
        """Update access statistics."""
        self.metadata.accessed_count += 1
        self.metadata.last_accessed = datetime.now()

    def update_keywords(self, keywords: list[str]) -> None:
        """Update keywords and mark as updated."""
        self.keywords = keywords
        self.metadata.updated_at = datetime.now()

    def format_for_prompt(self, max_length: int = 500) -> str:
        """Format entry for system prompt injection."""
        preview = self.content[:max_length] + ("..." if len(self.content) > max_length else "")
        type_indicator = f"[{self.type.value.upper()}]"
        tags_str = f" ({', '.join(self.metadata.tags[:3])})" if self.metadata.tags else ""
        return f"{type_indicator} **{self.title}**{tags_str}\n{preview}"


class MemoryIndex(BaseModel):
    """Index of all memory entries."""

    version: str = "1.0"
    last_scan: datetime | None = None
    entries: dict[str, MemoryEntry] = Field(default_factory=dict)
    total_scans: int = 0

    def add_entry(self, entry: MemoryEntry) -> None:
        """Add or update an entry in the index."""
        self.entries[entry.id] = entry

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an entry from the index."""
        if entry_id in self.entries:
            del self.entries[entry_id]
            return True
        return False

    def get_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Get all entries of a specific type."""
        return [e for e in self.entries.values() if e.type == memory_type]

    def get_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Get all entries with a specific tag."""
        return [e for e in self.entries.values() if tag in e.metadata.tags]

    def search(self, query: str, keywords: list[str] | None = None) -> list[MemoryEntry]:
        """Search entries by query string and optional keywords."""
        query_lower = query.lower()
        results = []
        for entry in self.entries.values():
            score = 0.0
            if query_lower in entry.title.lower():
                score += 2.0
            if query_lower in entry.content.lower():
                score += 1.0
            if keywords:
                for kw in keywords:
                    if kw.lower() in entry.keywords:
                        score += 0.5
                    if kw.lower() in entry.content.lower():
                        score += 0.3
            if score > 0:
                entry.relevance_score = score
                results.append(entry)
        return sorted(results, key=lambda e: e.relevance_score, reverse=True)
