"""Deterministic answer-level quality metrics for RAG evaluation fixtures."""

from __future__ import annotations

import re
import string
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_ENTITY_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&./-]+|[A-Z]{2,})"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&./-]+|[A-Z]{2,})){1,}\b"
)
_LEADING_ENTITY_STOPWORDS = {
    "Il",
    "La",
    "Lo",
    "I",
    "Gli",
    "Le",
    "L",
    "Un",
    "Una",
    "Della",
    "Del",
    "Dei",
    "Degli",
    "Nel",
    "Nella",
}
_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)


@dataclass(frozen=True)
class AnswerQualityMetrics:
    duplicate_block_ratio: float
    required_fact_coverage: float
    numeric_fact_coverage: float
    unsupported_entities: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class AnswerQualityCaseResult:
    case_id: str
    metrics: AnswerQualityMetrics


@dataclass(frozen=True)
class AnswerQualityReport:
    case_count: int
    average_duplicate_block_ratio: float
    average_required_fact_coverage: float
    average_numeric_fact_coverage: float
    unsupported_entity_count: int
    failed_case_count: int
    cases: tuple[AnswerQualityCaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def _normalize_for_duplicate(text: str) -> str:
    normalized = _normalize_whitespace(text).casefold()
    return normalized.translate(_PUNCT_TRANSLATION).strip()


def _normalize_for_match(text: str) -> str:
    return _normalize_whitespace(text).casefold()


def _paragraph_blocks(text: str) -> tuple[str, ...]:
    return tuple(block.strip() for block in re.split(r"\n\s*\n+", str(text or "")) if block.strip())


def _coverage(haystack: str, facts: Sequence[str]) -> float:
    requested = tuple(fact for fact in facts if str(fact or "").strip())
    if not requested:
        return 1.0
    normalized_haystack = _normalize_for_match(haystack)
    hits = sum(1 for fact in requested if _normalize_for_match(fact) in normalized_haystack)
    return round(hits / len(requested), 4)


def _numeric_coverage(answer: str, context: str, numeric_facts: Sequence[str]) -> float:
    requested = tuple(fact for fact in numeric_facts if str(fact or "").strip())
    if not requested:
        return 1.0
    normalized_answer = _normalize_for_match(answer)
    normalized_context = _normalize_for_match(context)
    hits = sum(
        1
        for fact in requested
        if (normalized_fact := _normalize_for_match(fact)) in normalized_answer
        and normalized_fact in normalized_context
    )
    return round(hits / len(requested), 4)


def _duplicate_block_ratio(answer: str) -> float:
    blocks = tuple(
        normalized
        for block in _paragraph_blocks(answer)
        if (normalized := _normalize_for_duplicate(block))
    )
    if not blocks:
        return 0.0

    seen: set[str] = set()
    duplicate_count = 0
    for block in blocks:
        if block in seen:
            duplicate_count += 1
        else:
            seen.add(block)
    return round(duplicate_count / len(blocks), 4)


def _trim_entity_candidate(candidate: str) -> str:
    parts = candidate.split()
    while len(parts) > 1 and parts[0] in _LEADING_ENTITY_STOPWORDS:
        parts = parts[1:]
    return " ".join(parts)


def _unsupported_entities(answer: str, context: str) -> tuple[str, ...]:
    normalized_context = _normalize_for_match(context)
    entities: list[str] = []
    seen: set[str] = set()
    for match in _ENTITY_RE.finditer(str(answer or "")):
        candidate = _trim_entity_candidate(match.group(0).strip(" ,.;:()[]{}"))
        if not candidate or any(char.isdigit() for char in candidate):
            continue
        if len(candidate.split()) < 2:
            continue
        normalized = _normalize_for_match(candidate)
        if normalized in seen or normalized in normalized_context:
            continue
        seen.add(normalized)
        entities.append(candidate)
    return tuple(entities)


def evaluate_answer_quality(
    *,
    answer: str,
    context: str,
    required_facts: Sequence[str],
    numeric_facts: Sequence[str] = (),
    duplicate_threshold: float = 0.08,
    min_required_fact_coverage: float = 1.0,
    min_numeric_fact_coverage: float = 0.8,
) -> AnswerQualityMetrics:
    """Evaluate an answer against deterministic quality gates."""

    duplicate_ratio = _duplicate_block_ratio(answer)
    required_fact_coverage = _coverage(answer, required_facts)
    numeric_fact_coverage = _numeric_coverage(answer, context, numeric_facts)
    unsupported_entities = _unsupported_entities(answer, context)

    failures: list[str] = []
    if duplicate_ratio > duplicate_threshold:
        failures.append("duplicate_blocks")
    if required_fact_coverage < min_required_fact_coverage:
        failures.append("required_fact_coverage")
    if numeric_fact_coverage < min_numeric_fact_coverage:
        failures.append("numeric_fact_coverage")
    if unsupported_entities:
        failures.append("unsupported_entities")

    return AnswerQualityMetrics(
        duplicate_block_ratio=duplicate_ratio,
        required_fact_coverage=required_fact_coverage,
        numeric_fact_coverage=numeric_fact_coverage,
        unsupported_entities=unsupported_entities,
        failures=tuple(failures),
    )


def _case_id(case: Mapping[str, Any], index: int) -> str:
    value = str(case.get("id") or case.get("case_id") or "").strip()
    return value or f"case-{index + 1}"


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def evaluate_answer_quality_cases(cases: Sequence[Mapping[str, Any]]) -> AnswerQualityReport:
    results: list[AnswerQualityCaseResult] = []
    for index, case in enumerate(cases):
        metrics = evaluate_answer_quality(
            answer=str(case.get("answer") or ""),
            context=str(case.get("context") or ""),
            required_facts=tuple(case.get("required_facts") or ()),
            numeric_facts=tuple(case.get("numeric_facts") or ()),
        )
        results.append(AnswerQualityCaseResult(case_id=_case_id(case, index), metrics=metrics))

    return AnswerQualityReport(
        case_count=len(results),
        average_duplicate_block_ratio=_average(
            [result.metrics.duplicate_block_ratio for result in results]
        ),
        average_required_fact_coverage=_average(
            [result.metrics.required_fact_coverage for result in results]
        ),
        average_numeric_fact_coverage=_average(
            [result.metrics.numeric_fact_coverage for result in results]
        ),
        unsupported_entity_count=sum(
            len(result.metrics.unsupported_entities) for result in results
        ),
        failed_case_count=sum(1 for result in results if result.metrics.failures),
        cases=tuple(results),
    )
