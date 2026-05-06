"""Grounded verification for extracted requirement candidates."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.tender_requirements import normalize_requirement_text

VERIFICATION_METHOD = "grounded_quote_overlap_v1"
VERIFIED = "verified"
DOWNGRADED = "downgraded"
REJECTED = "rejected"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "con",
    "da",
    "de",
    "dei",
    "del",
    "della",
    "delle",
    "di",
    "e",
    "for",
    "gli",
    "i",
    "il",
    "in",
    "is",
    "la",
    "le",
    "lo",
    "must",
    "of",
    "or",
    "shall",
    "the",
    "to",
    "un",
    "una",
    "with",
}


def _tokenize(value: str) -> set[str]:
    normalized = normalize_requirement_text(value)
    return {
        token
        for token in _TOKEN_RE.findall(normalized)
        if len(token) > 1 and token not in _STOPWORDS
    }


def _normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None


def _citation_quote(citation: Mapping[str, Any]) -> str:
    for key in ("quote", "excerpt", "source_quote", "text"):
        value = str(citation.get(key) or "").strip()
        if value:
            return re.sub(r"\s+", " ", value)
    return ""


def _quote_in_source(quote: str, source_text: str | None) -> bool:
    if source_text is None:
        return True
    normalized_quote = normalize_requirement_text(quote)
    normalized_source = normalize_requirement_text(source_text)
    return bool(normalized_quote and normalized_quote in normalized_source)


def _verification_payload(
    *,
    state: str,
    score: float,
    reason: str,
    citation_count: int,
    best_quote: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": VERIFICATION_METHOD,
        "state": state,
        "score": round(score, 4),
        "reason": reason,
        "citation_count": citation_count,
    }
    if best_quote:
        payload["best_quote"] = best_quote
    return payload


def verify_requirement_candidate(
    candidate: Mapping[str, Any],
    *,
    source_text: str | None = None,
    verified_threshold: float = 0.55,
    downgraded_threshold: float = 0.25,
) -> dict[str, Any]:
    """Return a candidate copy enriched with grounded verification metadata."""

    enriched = dict(candidate)
    summary = str(enriched.get("summary") or enriched.get("requirement_text") or "").strip()
    citations = [
        item for item in list(enriched.get("citations") or []) if isinstance(item, Mapping)
    ]
    summary_tokens = _tokenize(summary)

    if not summary_tokens:
        verification = _verification_payload(
            state=REJECTED,
            score=0.0,
            reason="empty_requirement_text",
            citation_count=len(citations),
        )
    elif not citations:
        verification = _verification_payload(
            state=REJECTED,
            score=0.0,
            reason="missing_citations",
            citation_count=0,
        )
    else:
        best_score = 0.0
        best_quote = ""
        quote_missing_from_source = False
        for citation in citations:
            quote = _citation_quote(citation)
            if not quote:
                continue
            if not _quote_in_source(quote, source_text):
                quote_missing_from_source = True
                continue
            quote_tokens = _tokenize(quote)
            if not quote_tokens:
                continue
            score = len(summary_tokens & quote_tokens) / len(summary_tokens)
            if score > best_score:
                best_score = score
                best_quote = quote

        if best_score >= verified_threshold:
            verification = _verification_payload(
                state=VERIFIED,
                score=best_score,
                reason="supported_by_citation",
                citation_count=len(citations),
                best_quote=best_quote,
            )
        elif best_score >= downgraded_threshold:
            verification = _verification_payload(
                state=DOWNGRADED,
                score=best_score,
                reason="partially_supported_by_citation",
                citation_count=len(citations),
                best_quote=best_quote,
            )
        else:
            verification = _verification_payload(
                state=REJECTED,
                score=best_score,
                reason="citation_quote_not_in_source"
                if quote_missing_from_source
                else "insufficient_citation_overlap",
                citation_count=len(citations),
                best_quote=best_quote or None,
            )

    confidence = _normalize_confidence(enriched.get("confidence"))
    if verification["state"] == DOWNGRADED:
        enriched["confidence"] = min(confidence if confidence is not None else 0.45, 0.45)
    elif verification["state"] == REJECTED:
        enriched["confidence"] = 0.0
    elif confidence is not None:
        enriched["confidence"] = confidence

    enriched["verification"] = verification
    enriched["verification_state"] = verification["state"]
    enriched["grounded_score"] = verification["score"]
    return enriched


def verify_requirement_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_text: str | None = None,
) -> list[dict[str, Any]]:
    """Verify a batch of extracted requirement candidates."""

    return [
        verify_requirement_candidate(candidate, source_text=source_text) for candidate in candidates
    ]
