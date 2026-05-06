"""Recall/precision baseline helpers for HybridRAG retrieval."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BASELINE_RETRIEVER_KEYS = ("dense", "sparse", "graph")
DEFAULT_BASELINE_RETRIEVERS = {"dense": True, "sparse": True, "graph": False}
DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS = (0, -3, -4, -5)


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    query: str
    expected_answer_keywords: tuple[str, ...]
    source_pages: tuple[int, ...] = ()
    ontology_domain: str | None = None
    source_chunk_hint: str | None = None
    difficulty: str | None = None


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    query: str
    recall_hit: bool
    precision_at_k: float
    source_page_hit: bool
    exact_source_page_hit: bool
    latency_ms: float
    expected_keywords: tuple[str, ...]
    hit_keywords: tuple[str, ...]
    hit_keyword_count: int
    retrieved_pages: tuple[int, ...]
    matched_source_pages: tuple[int, ...]
    retrieved_sources: tuple[dict[str, Any], ...]
    graph_source_count: int
    ontology_domain: str | None = None
    difficulty: str | None = None


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    case_count: int
    top_k: int
    precision_k: int
    retrievers: dict[str, bool]
    fusion_weights: dict[str, float]
    recall_at_k: float
    precision_at_k: float
    source_page_hit_rate: float
    exact_source_page_hit_rate: float
    graph_source_count: int
    graph_case_count: int
    average_latency_ms: float
    source_page_alias_offsets: tuple[int, ...]
    cases: tuple[RetrievalCaseResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _as_int_tuple(value: Any) -> tuple[int, ...]:
    values = value if isinstance(value, list | tuple) else [value]
    cleaned: list[int] = []
    for item in values:
        if item in (None, ""):
            continue
        try:
            cleaned.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(cleaned)


def _as_text_tuple(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list | tuple) else [value]
    return tuple(text for text in (_clean_text(item) for item in values) if text)


def _case_from_mapping(payload: Mapping[str, Any], index: int) -> RetrievalEvaluationCase:
    case_id = _clean_text(payload.get("id") or payload.get("case_id") or f"case-{index + 1}")
    query = _clean_text(payload.get("query"))
    keywords = _as_text_tuple(payload.get("expected_answer_keywords"))
    if not query:
        raise ValueError(f"Retrieval evaluation case {case_id!r} must define a query.")
    if not keywords:
        raise ValueError(
            f"Retrieval evaluation case {case_id!r} must define expected_answer_keywords."
        )
    return RetrievalEvaluationCase(
        case_id=case_id,
        query=query,
        expected_answer_keywords=keywords,
        source_pages=_as_int_tuple(payload.get("source_pages")),
        ontology_domain=_clean_text(payload.get("ontology_domain")) or None,
        source_chunk_hint=_clean_text(payload.get("source_chunk_hint")) or None,
        difficulty=_clean_text(payload.get("difficulty")) or None,
    )


def load_retrieval_evaluation_set(path: str | Path) -> list[RetrievalEvaluationCase]:
    """Load curated retrieval cases from either list JSON or an envelope."""

    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)

    raw_cases = payload.get("cases") if isinstance(payload, Mapping) else payload

    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Retrieval evaluation set must contain a non-empty case list.")

    cases: list[RetrievalEvaluationCase] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, Mapping):
            raise ValueError(f"Retrieval evaluation case #{index + 1} must be an object.")
        cases.append(_case_from_mapping(item, index))
    return cases


def _source_text(source: Mapping[str, Any]) -> str:
    return _clean_text(source.get("text") or source.get("content") or source.get("chunk"))


def _source_page(source: Mapping[str, Any]) -> int | None:
    metadata = source.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    for key in ("page_number", "page", "source_page"):
        value = source.get(key, metadata.get(key))
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_page_alias_offsets(offsets: Sequence[int] | None) -> tuple[int, ...]:
    raw_offsets = DEFAULT_SOURCE_PAGE_ALIAS_OFFSETS if offsets is None else offsets or (0,)

    normalized: list[int] = []
    for value in raw_offsets:
        try:
            offset = int(value)
        except (TypeError, ValueError):
            continue
        if offset not in normalized:
            normalized.append(offset)

    if 0 not in normalized:
        normalized.insert(0, 0)
    return tuple(normalized)


def _matched_source_pages(
    expected_pages: Sequence[int],
    retrieved_pages: Sequence[int],
    page_alias_offsets: Sequence[int],
) -> tuple[int, ...]:
    expected = set(expected_pages)
    if not expected:
        return ()

    retrieved_aliases = {
        page + offset
        for page in retrieved_pages
        for offset in page_alias_offsets
        if page + offset > 0
    }
    return tuple(sorted(expected & retrieved_aliases))


def _result_sources(result: Any) -> list[Mapping[str, Any]]:
    sources = (
        result.get("sources") if isinstance(result, Mapping) else getattr(result, "sources", None)
    )
    if not isinstance(sources, list):
        return []
    return [source for source in sources if isinstance(source, Mapping)]


def _keyword_hits(
    case: RetrievalEvaluationCase,
    sources: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    source_blob = "\n".join(_source_text(source).casefold() for source in sources)
    return tuple(
        keyword for keyword in case.expected_answer_keywords if keyword.casefold() in source_blob
    )


def _source_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = source.get("metadata")
    source_scores = source.get("source_scores")
    return {
        "text": _source_text(source),
        "score": source.get("score"),
        "page": _source_page(source),
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
        "retriever_sources": list(source.get("retriever_sources") or []),
        "source_scores": dict(source_scores) if isinstance(source_scores, Mapping) else {},
    }


def _source_has_retriever(source: Mapping[str, Any], retriever: str) -> bool:
    retriever_sources = source.get("retriever_sources")
    if (
        isinstance(retriever_sources, Sequence)
        and not isinstance(retriever_sources, str | bytes)
        and retriever in {str(item) for item in retriever_sources}
    ):
        return True

    source_scores = source.get("source_scores")
    return isinstance(source_scores, Mapping) and retriever in source_scores


def baseline_retriever_selection(retrievers: Mapping[str, bool] | None = None) -> dict[str, bool]:
    """Resolve baseline retrievers without letting graph re-enable by empty fallback."""

    if retrievers is None:
        return dict(DEFAULT_BASELINE_RETRIEVERS)

    selection = {key: False for key in BASELINE_RETRIEVER_KEYS}
    for key in BASELINE_RETRIEVER_KEYS:
        if key in retrievers:
            selection[key] = bool(retrievers[key])

    if any(selection.values()):
        return selection
    return dict(DEFAULT_BASELINE_RETRIEVERS)


def _filters_for_case(
    filters: Mapping[str, Any] | None,
    case: RetrievalEvaluationCase,
    retriever_selection: Mapping[str, bool],
) -> dict[str, Any]:
    case_filters = dict(filters or {})
    if retriever_selection.get("graph") and case.ontology_domain:
        case_filters["graph_ontology_domain"] = case.ontology_domain
    return case_filters


async def evaluate_retrieval_baseline(
    engine: Any,
    cases: Sequence[RetrievalEvaluationCase],
    *,
    top_k: int = 5,
    precision_k: int = 3,
    filters: Mapping[str, Any] | None = None,
    tender_id: int | None = None,
    retrievers: Mapping[str, bool] | None = None,
    fusion_weights: Mapping[str, float] | None = None,
    source_page_alias_offsets: Sequence[int] | None = None,
) -> RetrievalEvaluationReport:
    """Run search-only RAG retrieval over curated cases and compute baseline metrics."""

    from app.rag.engine import QueryMode, RAGQuery

    case_results: list[RetrievalCaseResult] = []
    normalized_top_k = max(1, int(top_k))
    normalized_precision_k = max(1, int(precision_k))
    retriever_selection = baseline_retriever_selection(retrievers)
    resolved_fusion_weights = dict(fusion_weights or {})
    normalized_page_alias_offsets = _normalize_page_alias_offsets(source_page_alias_offsets)

    for case in cases:
        case_filters = _filters_for_case(filters, case, retriever_selection)
        started = time.perf_counter()
        result = await engine.query(
            RAGQuery(
                text=case.query,
                mode=QueryMode.SEARCH,
                top_k=normalized_top_k,
                retrieval_top_k=normalized_top_k,
                filters=case_filters,
                tender_id=tender_id,
                retrievers=dict(retriever_selection),
                fusion_weights=dict(resolved_fusion_weights),
            )
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        sources = _result_sources(result)[:normalized_top_k]
        precision_sources = sources[:normalized_precision_k]
        hit_keywords = _keyword_hits(case, sources)
        precision_hit_keywords = _keyword_hits(case, precision_sources)
        retrieved_pages = tuple(
            page for page in (_source_page(source) for source in sources) if page
        )
        exact_source_page_hit = bool(set(case.source_pages) & set(retrieved_pages))
        matched_source_pages = _matched_source_pages(
            case.source_pages,
            retrieved_pages,
            normalized_page_alias_offsets,
        )
        source_page_hit = bool(matched_source_pages)
        graph_source_count = sum(1 for source in sources if _source_has_retriever(source, "graph"))

        case_results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                query=case.query,
                recall_hit=bool(hit_keywords),
                precision_at_k=_safe_ratio(
                    len(precision_hit_keywords),
                    len(case.expected_answer_keywords),
                ),
                source_page_hit=source_page_hit,
                exact_source_page_hit=exact_source_page_hit,
                latency_ms=latency_ms,
                expected_keywords=case.expected_answer_keywords,
                hit_keywords=hit_keywords,
                hit_keyword_count=len(hit_keywords),
                retrieved_pages=retrieved_pages,
                matched_source_pages=matched_source_pages,
                retrieved_sources=tuple(_source_summary(source) for source in sources),
                graph_source_count=graph_source_count,
                ontology_domain=case.ontology_domain,
                difficulty=case.difficulty,
            )
        )

    return RetrievalEvaluationReport(
        case_count=len(case_results),
        top_k=normalized_top_k,
        precision_k=normalized_precision_k,
        retrievers=dict(retriever_selection),
        fusion_weights=dict(resolved_fusion_weights),
        recall_at_k=_safe_ratio(
            sum(1 for item in case_results if item.recall_hit),
            len(case_results),
        ),
        precision_at_k=round(
            sum(item.precision_at_k for item in case_results) / len(case_results),
            4,
        )
        if case_results
        else 0.0,
        source_page_hit_rate=_safe_ratio(
            sum(1 for item in case_results if item.source_page_hit),
            len(case_results),
        ),
        exact_source_page_hit_rate=_safe_ratio(
            sum(1 for item in case_results if item.exact_source_page_hit),
            len(case_results),
        ),
        graph_source_count=sum(item.graph_source_count for item in case_results),
        graph_case_count=sum(1 for item in case_results if item.graph_source_count),
        average_latency_ms=round(
            sum(item.latency_ms for item in case_results) / len(case_results),
            3,
        )
        if case_results
        else 0.0,
        source_page_alias_offsets=normalized_page_alias_offsets,
        cases=tuple(case_results),
    )
