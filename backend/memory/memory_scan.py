"""Memory Scanner — scan .md files for MEMORY.md system integration."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.memory.memory_types import MemoryEntry, MemoryMetadata, MemoryType
from backend.memory.keyword_extractor import extract_keywords

logger = logging.getLogger("tenderclaw.memory.scan")

MEMORY_SECTIONS = {
    "# User Preferences": MemoryType.USER,
    "# User Memory": MemoryType.USER,
    "## User Preferences": MemoryType.USER,
    "## User Memory": MemoryType.USER,
    "# Feedback": MemoryType.FEEDBACK,
    "## Feedback": MemoryType.FEEDBACK,
    "# Project Context": MemoryType.PROJECT,
    "## Project Context": MemoryType.PROJECT,
    "# Reference": MemoryType.REFERENCE,
    "## Reference": MemoryType.REFERENCE,
    "# References": MemoryType.REFERENCE,
}

MEMORY_FILE_PATTERNS = [
    "MEMORY.md",
    "memory.md",
    ".memory.md",
    "CONTEXT.md",
    ".context.md",
]


class MemoryScanner:
    """Scans project files for memory entries."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root)
        self._section_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        self._entry_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
        self._tag_pattern = re.compile(r"\[([^\]]+)\]")

    def find_memory_files(self) -> list[Path]:
        """Find all memory-related markdown files in the project."""
        found: list[Path] = []
        for pattern in MEMORY_FILE_PATTERNS:
            found.extend(self.project_root.rglob(pattern))
        return sorted(set(found))

    def scan_file(self, file_path: Path) -> list[MemoryEntry]:
        """Scan a single markdown file and extract memory entries."""
        entries: list[MemoryEntry] = []
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", file_path, exc)
            return entries

        current_section: str | None = None
        current_type = MemoryType.PROJECT
        current_tags: list[str] = []
        line_num = 0

        for line_num, line in enumerate(content.splitlines(), 1):
            section_match = self._section_pattern.match(line)
            if section_match:
                current_section = section_match.group(2).strip()
                current_type = self._detect_type(current_section)
                current_tags = self._extract_tags_from_section(current_section)
                continue

            if line.strip().startswith("-") or line.strip().startswith("*"):
                entry_text = line.lstrip("-*").strip()
                if entry_text and len(entry_text) > 5:
                    entry = self._create_entry(
                        entry_text, current_type, current_tags, str(file_path), line_num
                    )
                    if entry:
                        entries.append(entry)

        logger.info("Scanned %s: found %d entries", file_path.name, len(entries))
        return entries

    def scan_project(self) -> list[MemoryEntry]:
        """Scan all memory files in the project."""
        all_entries: list[MemoryEntry] = []
        for memory_file in self.find_memory_files():
            entries = self.scan_file(memory_file)
            all_entries.extend(entries)
        return all_entries

    def _detect_type(self, section: str) -> MemoryType:
        """Detect memory type from section header."""
        section_lower = section.lower()
        if "user" in section_lower:
            return MemoryType.USER
        if "feedback" in section_lower:
            return MemoryType.FEEDBACK
        if "reference" in section_lower:
            return MemoryType.REFERENCE
        return MemoryType.PROJECT

    def _extract_tags_from_section(self, section: str) -> list[str]:
        """Extract tags from section name."""
        tags = self._tag_pattern.findall(section)
        keywords = extract_keywords(section, top_n=5)
        return list(set(tags + keywords))

    def _create_entry(
        self,
        content: str,
        memory_type: MemoryType,
        tags: list[str],
        source: str,
        line: int,
    ) -> MemoryEntry | None:
        """Create a memory entry from content."""
        if len(content) < 10:
            return None

        keywords = extract_keywords(content, top_n=10)
        title = self._extract_title(content)

        entry_id = self._generate_id(content, line)

        return MemoryEntry(
            id=entry_id,
            type=memory_type,
            title=title,
            content=content,
            keywords=keywords,
            metadata=MemoryMetadata(
                source_file=source,
                line_number=line,
                tags=tags,
                created_at=datetime.now(),
            ),
        )

    def _extract_title(self, content: str) -> str:
        """Extract a title from entry content."""
        clean = content.strip()
        if len(clean) > 60:
            clean = clean[:57] + "..."
        return clean

    def _generate_id(self, content: str, line: int) -> str:
        """Generate a unique ID for an entry."""
        prefix = content[:20].lower().replace(" ", "_")[:20]
        return f"mem_{prefix}_{line}_{datetime.now().strftime('%H%M%S')}"


def score_memory_relevance(entry: MemoryEntry, keywords: list[str], query: str) -> float:
    """Calculate relevance score for a memory entry."""
    score = entry.relevance_score
    query_lower = query.lower()

    if query_lower in entry.title.lower():
        score += 3.0
    if query_lower in entry.content.lower():
        score += 1.5

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in entry.keywords:
            score += 1.0
        if kw_lower in entry.title.lower():
            score += 0.8
        if kw_lower in entry.content.lower():
            score += 0.4
        if kw_lower in entry.metadata.tags:
            score += 1.5

    if entry.metadata.priority > 0:
        score += entry.metadata.priority * 0.5

    entry.relevance_score = score
    return score


def get_scanner(project_root: str = ".") -> MemoryScanner:
    """Get a configured memory scanner."""
    return MemoryScanner(Path(project_root))
