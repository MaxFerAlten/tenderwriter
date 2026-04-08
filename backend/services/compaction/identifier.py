"""Identifier Preservation for Compaction.

Ported from OpenClaw's compaction-safeguard-quality.ts.
Preserves important identifiers (IDs, URLs, file paths, etc.) in summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# Maximum identifiers to extract
MAX_EXTRACTED_IDENTIFIERS = 50

# Patterns for identifier extraction
IDENTIFIER_PATTERNS = [
    # Git hashes, IDs (8+ hex chars)
    r"\b([A-Fa-f0-9]{8,})\b",
    # URLs
    r"(https?://\S+)",
    # Unix file paths
    r"(/[\w.-]+(?:/[\w.-]+)*(?:\.\w+)?)",
    # Windows file paths
    r"([A-Za-z]:\\[\w\\.-]+(?:\\[\w\\.-]+)*)",
    # URLs in markdown
    r"\[([^\]]+)\]\((https?://[^\)]+)\)",
    # Port numbers
    r"(\w+\.[\w.-]+:\d{1,5})",
    # Long numbers (IDs, timestamps)
    r"\b(\d{6,})\b",
]


class IdentifierPolicy(str, Enum):
    """Identifier preservation policy."""

    STRICT = "strict"  # Preserve all identifiers exactly
    OFF = "off"  # No enforcement
    CUSTOM = "custom"  # Operator-defined policy


@dataclass
class ExtractedIdentifier:
    """An extracted identifier with context."""

    value: str
    normalized: str
    context: Optional[str] = None


def extract_identifiers(
    text: str,
    max_count: int = MAX_EXTRACTED_IDENTIFIERS,
) -> List[ExtractedIdentifier]:
    """Extract opaque identifiers from text.

    Identifiers include: IDs, URLs, file paths, ports, hashes, dates, times.
    """
    identifiers: List[ExtractedIdentifier] = []
    seen: Set[str] = set()

    # Apply patterns
    for pattern in IDENTIFIER_PATTERNS:
        matches = re.findall(pattern, text)
        for match in matches:
            # Handle tuple matches (from markdown links)
            value = match if isinstance(match, str) else match[-1]

            if not value or len(value) < 4:
                continue

            # Normalize
            normalized = value.lower().strip()

            if normalized in seen:
                continue

            seen.add(normalized)
            identifiers.append(ExtractedIdentifier(
                value=value,
                normalized=normalized,
            ))

            if len(identifiers) >= max_count:
                return identifiers

    return identifiers


def validate_identifier_preservation(
    summary: str,
    identifiers: List[ExtractedIdentifier],
    policy: IdentifierPolicy,
) -> Tuple[bool, List[str]]:
    """Validate that summary preserves required identifiers.

    Returns (is_valid, list_of_violations).
    """
    if policy == IdentifierPolicy.OFF:
        return True, []

    violations: List[str] = []

    for identifier in identifiers:
        # Check if value appears in summary
        if identifier.value not in summary:
            # Check if normalized form appears
            if identifier.normalized not in summary.lower():
                violations.append(identifier.value)

    is_valid = len(violations) == 0

    if policy == IdentifierPolicy.STRICT and violations:
        # In strict mode, missing identifiers is a violation
        return False, violations[:5]  # Limit to first 5

    return is_valid, violations


def format_identifier_section(
    identifiers: List[ExtractedIdentifier],
    policy: IdentifierPolicy,
) -> str:
    """Format identifiers as a section for summarization prompt."""
    if not identifiers:
        return ""

    lines = ["## Exact Identifiers\n"]

    if policy == IdentifierPolicy.STRICT:
        lines.append("(Preserve these exactly as-is)\n")

    for identifier in identifiers[:MAX_EXTRACTED_IDENTIFIERS]:
        lines.append(f"- {identifier.value}")

    return "\n".join(lines)


def generate_identifier_instructions(policy: IdentifierPolicy) -> str:
    """Generate instruction text for identifier preservation."""
    if policy == IdentifierPolicy.STRICT:
        return (
            "For ## Exact identifiers, preserve literal values exactly as seen "
            "(IDs, URLs, file paths, ports, hashes, dates, times). "
            "Do not modify, abbreviate, or paraphrase these values."
        )
    elif policy == IdentifierPolicy.OFF:
        return (
            "For ## Exact identifiers, include identifiers only when needed "
            "for continuity; do not enforce literal-preservation rules."
        )
    else:
        return (
            "Preserve important identifiers (IDs, URLs, file paths) as needed "
            "for context continuity."
        )


def filter_high_value_identifiers(
    identifiers: List[ExtractedIdentifier],
    recent_text: str,
    max_count: int = 20,
) -> List[ExtractedIdentifier]:
    """Filter identifiers to those most likely needed in summary.

    Prioritizes identifiers that appear in recent context.
    """
    scored: List[Tuple[int, ExtractedIdentifier]] = []

    for identifier in identifiers:
        # Count occurrences in recent text
        count = recent_text.lower().count(identifier.normalized)
        # Boost score for recent mentions
        score = count * 10
        # Short IDs are more valuable
        if len(identifier.value) < 20:
            score += 5
        # URLs are always valuable
        if identifier.value.startswith("http"):
            score += 10

        scored.append((score, identifier))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top N
    return [ident for _, ident in scored[:max_count]]
