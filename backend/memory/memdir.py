"""MEMORY.md Directory — advanced memory index management.

This module provides:
- MEMORY.md index management
- Memory taxonomy (user/feedback/project/reference)
- findRelevantMemories() for relevance search
- Memory scanning with scoring
- Auto-memory with daily logs
- Context search capability
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.memory.memory_types import MemoryEntry, MemoryIndex, MemoryMetadata, MemoryType
from backend.memory.memory_scan import MemoryScanner, score_memory_relevance, get_scanner
from backend.memory.keyword_extractor import extract_keywords
from backend.memory.team_mem import read_team_memory, build_team_memory_prompt

logger = logging.getLogger("tenderclaw.memory.memdir")

MEMORY_INDEX_FILE = ".tenderclaw/memory_index.json"
DAILY_LOG_DIR = ".tenderclaw/daily_logs"


class MemoryDirectory:
    """Manages the MEMORY.md index and provides memory search capabilities."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root)
        self.index_path = self.project_root / MEMORY_INDEX_FILE
        self.daily_log_path = self.project_root / DAILY_LOG_DIR
        self.scanner = get_scanner(str(self.project_root))
        self.index = self._load_index()
        self._daily_log_buffer: list[str] = []

    def _load_index(self) -> MemoryIndex:
        """Load or create the memory index."""
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                return MemoryIndex.model_validate(data)
            except Exception as exc:
                logger.warning("Failed to load memory index: %s", exc)

        return MemoryIndex()

    def _save_index(self) -> None:
        """Persist the memory index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            self.index.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8"
        )

    def scan_and_index(self, force: bool = False) -> int:
        """Scan project for memory entries and update the index."""
        if not force and self.index.last_scan:
            time_since = datetime.now() - self.index.last_scan
            if time_since < timedelta(minutes=5):
                return len(self.index.entries)

        self.index.last_scan = datetime.now()
        self.index.total_scans += 1

        entries = self.scanner.scan_project()
        self.index.entries.clear()

        for entry in entries:
            self.index.add_entry(entry)

        self._save_index()
        logger.info("Indexed %d memory entries", len(entries))
        return len(entries)

    def find_relevant_memories(
        self,
        query: str,
        limit: int = 5,
        types: list[MemoryType] | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Find memories relevant to a query with scoring."""
        keywords = extract_keywords(query, top_n=10)

        candidates = list(self.index.entries.values())

        if types:
            candidates = [e for e in candidates if e.type in types]
        if tags:
            candidates = [e for e in candidates if any(t in e.metadata.tags for t in tags)]

        for entry in candidates:
            entry.relevance_score = score_memory_relevance(entry, keywords, query)

        scored = sorted(candidates, key=lambda e: e.relevance_score, reverse=True)
        results = scored[:limit]

        for entry in results:
            entry.touch()

        self._save_index()
        return results

    def find_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Get all memories of a specific type."""
        return self.index.get_by_type(memory_type)

    def find_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Get all memories with a specific tag."""
        return self.index.get_by_tag(tag)

    def search_context(
        self,
        context_text: str,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Search memories using extracted context keywords."""
        keywords = extract_keywords(context_text, top_n=15)
        query = " ".join(keywords)
        return self.find_relevant_memories(query, limit=limit)

    def add_memory(
        self,
        content: str,
        memory_type: MemoryType,
        title: str | None = None,
        tags: list[str] | None = None,
        priority: int = 0,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        keywords = extract_keywords(content, top_n=10)
        entry_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        entry = MemoryEntry(
            id=entry_id,
            type=memory_type,
            title=title or content[:50],
            content=content,
            keywords=keywords,
            metadata=MemoryMetadata(
                tags=tags or [],
                priority=priority,
                source_file="manual",
            ),
        )

        self.index.add_entry(entry)
        self._save_index()
        logger.info("Added memory entry: %s", entry_id)
        return entry

    def update_memory(self, entry_id: str, content: str) -> bool:
        """Update an existing memory entry."""
        if entry_id not in self.index.entries:
            return False

        entry = self.index.entries[entry_id]
        entry.content = content
        entry.keywords = extract_keywords(content, top_n=10)
        entry.metadata.updated_at = datetime.now()
        self._save_index()
        return True

    def delete_memory(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        result = self.index.remove_entry(entry_id)
        if result:
            self._save_index()
        return result

    def log_activity(self, activity: str) -> None:
        """Log an activity to the daily memory buffer."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._daily_log_buffer.append(f"[{timestamp}] {activity}")

    def flush_daily_log(self) -> Path | None:
        """Flush the daily log buffer to disk."""
        if not self._daily_log_buffer:
            return None

        self.daily_log_path.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = self.daily_log_path / f"{date_str}.md"

        header = f"# Daily Log - {date_str}\n\n"
        content = header + "\n".join(self._daily_log_buffer) + "\n"

        try:
            if log_file.exists():
                existing = log_file.read_text(encoding="utf-8")
                content = existing + "\n" + "\n".join(self._daily_log_buffer) + "\n"

            log_file.write_text(content, encoding="utf-8")
            self._daily_log_buffer.clear()
            logger.info("Flushed daily log to %s", log_file.name)
            return log_file
        except Exception as exc:
            logger.error("Failed to flush daily log: %s", exc)
            return None

    def get_recent_logs(self, days: int = 7) -> list[dict[str, Any]]:
        """Get recent daily logs."""
        logs: list[dict[str, Any]] = []
        if not self.daily_log_path.exists():
            return logs

        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            log_file = self.daily_log_path / f"{date.strftime('%Y-%m-%d')}.md"
            if log_file.exists():
                try:
                    content = log_file.read_text(encoding="utf-8")
                    logs.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "path": str(log_file),
                        "content": content,
                    })
                except Exception as exc:
                    logger.warning("Failed to read log %s: %s", log_file, exc)

        return logs

    def format_for_system_prompt(
        self,
        query: str,
        limit: int = 5,
        include_team: bool = True,
    ) -> str:
        """Format relevant memories for injection into system prompt."""
        parts: list[str] = []

        memories = self.find_relevant_memories(query, limit=limit)
        if memories:
            sections: dict[MemoryType, list[str]] = {t: [] for t in MemoryType}
            for mem in memories:
                formatted = mem.format_for_prompt(max_length=200)
                sections[mem.type].append(formatted)

            parts.append("\n## Relevant Memories")

            type_labels = {
                MemoryType.USER: "User Preferences",
                MemoryType.FEEDBACK: "Feedback History",
                MemoryType.PROJECT: "Project Context",
                MemoryType.REFERENCE: "References",
            }

            for mtype, items in sections.items():
                if items:
                    parts.append(f"\n### {type_labels.get(mtype, mtype.value)}")
                    for item in items:
                        parts.append(f"- {item}")

        if include_team:
            team_context = build_team_memory_prompt(str(self.project_root))
            if team_context:
                parts.append(team_context)

        return "\n".join(parts)

    def get_stats(self) -> dict[str, Any]:
        """Get memory system statistics."""
        by_type: dict[str, int] = {}
        by_tag: dict[str, int] = {}

        for entry in self.index.entries.values():
            by_type[entry.type.value] = by_type.get(entry.type.value, 0) + 1
            for tag in entry.metadata.tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1

        return {
            "total_entries": len(self.index.entries),
            "by_type": by_type,
            "by_tag": by_tag,
            "last_scan": self.index.last_scan.isoformat() if self.index.last_scan else None,
            "total_scans": self.index.total_scans,
            "daily_log_buffer_size": len(self._daily_log_buffer),
        }


_memdir_cache: dict[str, MemoryDirectory] = {}


def get_memory_directory(project_root: str = ".") -> MemoryDirectory:
    """Get or create a memory directory instance for the project."""
    if project_root not in _memdir_cache:
        _memdir_cache[project_root] = MemoryDirectory(project_root)
    return _memdir_cache[project_root]


def find_relevant_memories(
    query: str,
    project_root: str = ".",
    limit: int = 5,
    types: list[MemoryType] | None = None,
) -> list[MemoryEntry]:
    """Convenience function to find relevant memories."""
    memdir = get_memory_directory(project_root)
    memdir.scan_and_index()
    return memdir.find_relevant_memories(query, limit=limit, types=types)


def format_memories_for_prompt(
    query: str,
    project_root: str = ".",
    limit: int = 5,
) -> str:
    """Convenience function to format memories for system prompt."""
    memdir = get_memory_directory(project_root)
    memdir.scan_and_index()
    return memdir.format_for_system_prompt(query, limit=limit)
