"""Deterministic document-quality helpers for ingestion metadata."""

from __future__ import annotations

import re

NUMERIC_MENTION_PATTERNS = (
    r"\b\d{1,4}\s+(?:giorni|mesi|anni)\b",
    r"\bEuro\s*[\d.,]+",
    r"\b\d{1,3}\s*%",
    r"\bart\.?\s*\d+[^\s,.;)]*(?:\s*c\.c\.)?",
)

_NUMERIC_MENTION_RES = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in NUMERIC_MENTION_PATTERNS
)
_BROKEN_NUMERIC_FRAGMENT_RE = re.compile(
    r"\b(?:entro|massimo|almeno|durata(?:\s+di)?|per)\s+"
    r"(?:giorni|mesi|anni)\b",
    re.IGNORECASE,
)


def _clean_mention(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,;:()[]")


def extract_numeric_mentions(text: str) -> tuple[str, ...]:
    mentions: list[str] = []
    seen: set[str] = set()
    for pattern in _NUMERIC_MENTION_RES:
        for match in pattern.finditer(str(text or "")):
            mention = _clean_mention(match.group(0))
            normalized = mention.casefold()
            if mention and normalized not in seen:
                seen.add(normalized)
                mentions.append(mention)
    return tuple(mentions)


def has_broken_numeric_fragment(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or ""))
    return bool(_BROKEN_NUMERIC_FRAGMENT_RE.search(normalized))


def document_quality_metadata(text: str) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = {}
    numeric_mentions = list(extract_numeric_mentions(text))
    if numeric_mentions:
        metadata["numeric_mentions"] = numeric_mentions

    parse_warnings: list[str] = []
    if has_broken_numeric_fragment(text):
        parse_warnings.append("broken_numeric_fragment")
    if parse_warnings:
        metadata["parse_warnings"] = parse_warnings

    return metadata
