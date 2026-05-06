"""Deterministic context hygiene helpers for RAG prompt construction."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_WORD_RE = re.compile(r"\b[\w-]{3,}\b", re.UNICODE)
_DEDUP_TOKEN_RE = re.compile(r"\b[\w-]+\b", re.UNICODE)
_NUMERIC_OR_LEGAL_RE = re.compile(
    r"\b\d{1,4}\s+(?:giorni|mesi|anni|days|months|years)\b"
    r"|\b(?:euro|eur)\s*[\d.,]+"
    r"|\b\d{1,3}\s*%"
    r"|\bCIG\s*[:\-]?\s*[A-Z0-9]{8,12}\b"
    r"|\b[0-9]{5,6}/20[0-9]{2}\b"
    r"|\bart\.?\s*\d+[^\s,.;)]*(?:\s*c\.c\.)?",
    re.IGNORECASE,
)
_BROAD_TENDER_QUERY_RE = re.compile(
    r"\b(?:riassum\w*|sintetizza\w*|overview|panoramica|spiega\w*|"
    r"descriv\w*|analizz\w*|dettagli?\b|elenco|lista)\b"
    r".*\b(?:gara|bando|capitolato|disciplinare|procedura|lotto|tender|rfp|appalto)\b"
    r"|\b(?:gara|bando|capitolato|disciplinare|procedura|lotto|tender|rfp|appalto)\b"
    r".*\b(?:riassum\w*|sintetizza\w*|overview|panoramica|spiega\w*|"
    r"descriv\w*|analizz\w*|dettagli?\b|elenco|lista)\b",
    re.IGNORECASE,
)
_TENDER_OVERVIEW_TERMS = {
    "acn",
    "capitolato",
    "cctt",
    "cloud",
    "contratto",
    "durata",
    "fornitore",
    "fornitura",
    "infrastruttura",
    "oggetto",
    "perimetro",
    "qualificazione",
    "requisiti",
    "servizi",
    "sistema",
}
_QUERY_STOPWORDS = {
    "che",
    "chi",
    "cosa",
    "come",
    "con",
    "dei",
    "del",
    "della",
    "delle",
    "dimmi",
    "gara",
    "gli",
    "per",
    "quale",
    "quali",
    "richiesta",
    "sono",
    "una",
}


def normalize_context_text(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _score(item: Mapping[str, Any]) -> float:
    value = item.get("score", 0.0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _dedup_tokens(text: str) -> set[str]:
    return set(_DEDUP_TOKEN_RE.findall(text))


def _token_similarity(candidate: str, existing: str) -> float:
    candidate_tokens = _dedup_tokens(candidate)
    existing_tokens = _dedup_tokens(existing)
    if not candidate_tokens or not existing_tokens:
        return 0.0
    return len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)


def _has_contained_tokens(candidate: str, existing: str) -> bool:
    candidate_tokens = _dedup_tokens(candidate)
    existing_tokens = _dedup_tokens(existing)
    if len(candidate_tokens) < 6 or len(existing_tokens) < 6:
        return False
    smaller, larger = (
        (candidate_tokens, existing_tokens)
        if len(candidate_tokens) <= len(existing_tokens)
        else (existing_tokens, candidate_tokens)
    )
    return smaller <= larger


def _is_duplicate(candidate: str, existing: str, similarity_threshold: float) -> bool:
    if candidate == existing:
        return True
    if not candidate or not existing:
        return False
    character_similarity = SequenceMatcher(None, candidate, existing).ratio()
    if character_similarity >= max(similarity_threshold, 0.88):
        return True
    return (
        _has_contained_tokens(candidate, existing) or _token_similarity(candidate, existing) >= 0.82
    )


def _merge_metadata(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(primary or {})
    for key, value in (secondary or {}).items():
        if key not in merged:
            merged[key] = value
    return merged


def _merge_ordered_values(
    primary: Any,
    secondary: Any,
) -> list[Any]:
    merged: list[Any] = []
    for value in (*list(primary or []), *list(secondary or [])):
        if value not in merged:
            merged.append(value)
    return merged


def _merge_source_scores(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
) -> dict[str, float]:
    merged: dict[str, float] = {}
    for scores in (secondary or {}, primary or {}):
        for source, value in scores.items():
            if not isinstance(value, (int, float)):
                continue
            merged[source] = max(merged.get(source, float("-inf")), float(value))
    return merged


def _merge_duplicate_context_item(
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    primary, secondary = (
        (candidate, existing) if _score(candidate) > _score(existing) else (existing, candidate)
    )
    merged = dict(primary)
    merged["metadata"] = _merge_metadata(
        primary.get("metadata", {}),
        secondary.get("metadata", {}),
    )
    merged["retriever_sources"] = _merge_ordered_values(
        primary.get("retriever_sources", []),
        secondary.get("retriever_sources", []),
    )
    merged["source_scores"] = _merge_source_scores(
        primary.get("source_scores", {}),
        secondary.get("source_scores", {}),
    )
    return merged


def deduplicate_context_items(
    items: Sequence[Mapping[str, Any]],
    *,
    similarity_threshold: float = 0.88,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Remove exact and near-duplicate context items while keeping the best score."""

    kept: list[dict[str, Any]] = []
    kept_normalized: list[str] = []
    removed = 0

    for item in items:
        candidate = dict(item)
        normalized = normalize_context_text(str(candidate.get("text") or ""))
        if not normalized:
            removed += 1
            continue

        duplicate_index = next(
            (
                index
                for index, existing in enumerate(kept_normalized)
                if _is_duplicate(normalized, existing, similarity_threshold)
            ),
            None,
        )

        if duplicate_index is None:
            kept.append(candidate)
            kept_normalized.append(normalized)
            continue

        removed += 1
        merged = _merge_duplicate_context_item(kept[duplicate_index], candidate)
        kept[duplicate_index] = merged
        kept_normalized[duplicate_index] = normalize_context_text(str(merged.get("text") or ""))

    return kept, {"input": len(items), "kept": len(kept), "removed": removed}


def _query_terms(query: str) -> set[str]:
    terms = {term.casefold() for term in _WORD_RE.findall(str(query or ""))}
    relevant = {term for term in terms if term not in _QUERY_STOPWORDS}
    if _BROAD_TENDER_QUERY_RE.search(str(query or "")):
        relevant.update(_TENDER_OVERVIEW_TERMS)
    return relevant


def _split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT_RE.split(str(text or ""))
        if sentence.strip()
    ]


def _sentence_matches_query(sentence: str, query_terms: set[str]) -> bool:
    normalized = normalize_context_text(sentence)
    return any(term in normalized for term in query_terms)


def compress_context_block(
    text: str,
    *,
    query: str,
    min_chars_to_compress: int = 0,
) -> str:
    """Select query-relevant context sentences without rewriting source text."""

    original = str(text or "").strip()
    if not original or len(original) < min_chars_to_compress:
        return original

    query_terms = _query_terms(query)
    selected: list[str] = []
    seen: set[str] = set()

    for sentence in _split_sentences(original):
        normalized = normalize_context_text(sentence)
        if normalized in seen:
            continue
        should_keep = _sentence_matches_query(sentence, query_terms) or bool(
            _NUMERIC_OR_LEGAL_RE.search(sentence)
        )
        if should_keep:
            seen.add(normalized)
            selected.append(sentence)

    return " ".join(selected) if selected else original
