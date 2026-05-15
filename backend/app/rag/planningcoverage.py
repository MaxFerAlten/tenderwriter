"""Tender-specific planning coverage retrieval helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.rag.internal_prompting import default_language
from app.rag.localization import get_planning_coverage_messages

_PC_MSGS = get_planning_coverage_messages(default_language())

PLANNING_COVERAGE_SETTINGS_KEY = "planningcoverage"


@dataclass(frozen=True)
class PlanningCoverageSlot:
    key: str
    label: str
    trigger_terms: tuple[str, ...]
    queries: tuple[str, ...]
    evidence_terms: tuple[str, ...]


@dataclass(frozen=True)
class PlanningCoveragePlan:
    query_class: str
    activated: bool
    slots_triggered: list[str]
    generated_queries: dict[str, list[str]]
    notes: list[str]


@dataclass(frozen=True)
class PlanningCoverageResult:
    activated: bool
    query_class: str
    slots_triggered: list[str]
    generated_queries: dict[str, list[str]]
    results: list[dict[str, Any]]
    notes: list[str]
    latency_ms: float


def _build_coverage_slots() -> dict[str, PlanningCoverageSlot]:
    msgs = _PC_MSGS
    slots: dict[str, PlanningCoverageSlot] = {}
    for key in msgs.slot_labels:
        slots[key] = PlanningCoverageSlot(
            key=key,
            label=msgs.slot_labels[key],
            trigger_terms=msgs.slot_triggers[key],
            queries=msgs.slot_queries[key],
            evidence_terms=msgs.slot_evidence[key],
        )
    return slots


PLANNING_COVERAGE_SLOTS: dict[str, PlanningCoverageSlot] = _build_coverage_slots()

DEFAULT_PLANNING_COVERAGE_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "adaptive",
    "slots": {
        key: slot.key in {"identification", "cig_lots", "amounts", "duration", "deadlines"}
        for key, slot in PLANNING_COVERAGE_SLOTS.items()
    },
    "retrievers": {"sparse": True, "dense": True, "graph": False},
    "topkPerSlot": 2,
    "maxSourcesPerSlot": 2,
    "globalMaxCoverageChunks": 8,
    "minScore": 0.2,
    "onlyTenderQueries": True,
    "alwaysRunPlanner": True,
}

_CIG_RE = re.compile(r"\bCIG\b|\b[A-Z][0-9A-Z]{8,}\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"(?:€|\beuro\b)\s*[\d.,]+|[\d.]+,\d{2}\s*(?:€|\beuro\b)", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"\b\d{1,4}\s*(?:%|giorni|mesi|anni)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def _deepcopy_defaults() -> dict[str, Any]:
    return {
        **DEFAULT_PLANNING_COVERAGE_CONFIG,
        "slots": dict(DEFAULT_PLANNING_COVERAGE_CONFIG["slots"]),
        "retrievers": dict(DEFAULT_PLANNING_COVERAGE_CONFIG["retrievers"]),
    }


def _as_bool_map(raw: Any, defaults: Mapping[str, bool]) -> dict[str, bool]:
    values = dict(defaults)
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if key in values:
                values[key] = bool(value)
    return values


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def normalize_planning_coverage_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = _deepcopy_defaults()
    incoming = dict(config or {})

    normalized["enabled"] = bool(incoming.get("enabled", normalized["enabled"]))
    mode = str(incoming.get("mode", normalized["mode"]) or "adaptive")
    normalized["mode"] = mode if mode in {"disabled", "adaptive", "always_on"} else "adaptive"
    normalized["slots"] = _as_bool_map(incoming.get("slots"), normalized["slots"])
    normalized["retrievers"] = _as_bool_map(incoming.get("retrievers"), normalized["retrievers"])
    normalized["topkPerSlot"] = _clamp_int(
        incoming.get("topkPerSlot"),
        default=2,
        minimum=1,
        maximum=10,
    )
    normalized["maxSourcesPerSlot"] = _clamp_int(
        incoming.get("maxSourcesPerSlot"),
        default=2,
        minimum=1,
        maximum=10,
    )
    normalized["globalMaxCoverageChunks"] = _clamp_int(
        incoming.get("globalMaxCoverageChunks"),
        default=8,
        minimum=1,
        maximum=30,
    )
    normalized["minScore"] = _clamp_float(
        incoming.get("minScore"),
        default=0.2,
        minimum=0.0,
        maximum=1.0,
    )
    normalized["onlyTenderQueries"] = bool(
        incoming.get("onlyTenderQueries", normalized["onlyTenderQueries"])
    )
    normalized["alwaysRunPlanner"] = bool(
        incoming.get("alwaysRunPlanner", normalized["alwaysRunPlanner"])
    )
    return normalized


def _normalized_text(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def query_is_tender_like(query: str) -> bool:
    normalized = _normalized_text(query)
    return any(term in normalized for term in _PC_MSGS.tender_query_terms)


def _slot_triggered_by_query(slot: PlanningCoverageSlot, normalized_query: str) -> bool:
    return any(term in normalized_query for term in slot.trigger_terms)


def classify_query_for_coverage(
    query: str,
    config: Mapping[str, Any] | None = None,
) -> PlanningCoveragePlan:
    cfg = normalize_planning_coverage_config(config)
    normalized_query = _normalized_text(query)
    tender_like = query_is_tender_like(query)

    if not cfg["enabled"] or cfg["mode"] == "disabled":
        return PlanningCoveragePlan(
            query_class=(
                "disabled"
                if cfg["mode"] == "disabled"
                else ("tender_structured" if tender_like else "generic")
            ),
            activated=False,
            slots_triggered=[],
            generated_queries={},
            notes=[_PC_MSGS.note_disabled],
        )

    if cfg["onlyTenderQueries"] and not tender_like:
        return PlanningCoveragePlan(
            query_class="generic",
            activated=False,
            slots_triggered=[],
            generated_queries={},
            notes=[_PC_MSGS.note_not_tender],
        )

    enabled_slots = [
        slot for key, slot in PLANNING_COVERAGE_SLOTS.items() if cfg["slots"].get(key, False)
    ]
    run_all_enabled = cfg["mode"] == "always_on" or (cfg["alwaysRunPlanner"] and tender_like)
    selected_slots = (
        enabled_slots
        if run_all_enabled
        else [slot for slot in enabled_slots if _slot_triggered_by_query(slot, normalized_query)]
    )

    generated_queries = {slot.key: list(slot.queries) for slot in selected_slots}
    notes = [
        _PC_MSGS.note_activated_tender
        if tender_like
        else _PC_MSGS.note_activated_always,
    ]
    if not selected_slots:
        notes.append(_PC_MSGS.note_no_slot_activated)

    return PlanningCoveragePlan(
        query_class="tender_structured" if tender_like else "forced",
        activated=bool(selected_slots),
        slots_triggered=[slot.key for slot in selected_slots],
        generated_queries=generated_queries,
        notes=notes,
    )


def _result_text(result: Any) -> str:
    if isinstance(result, Mapping):
        return str(result.get("text") or "")
    return str(getattr(result, "text", "") or "")


def _result_score(result: Any) -> float:
    value = (
        result.get("score", 0.0) if isinstance(result, Mapping) else getattr(result, "score", 0.0)
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _result_metadata(result: Any) -> dict[str, Any]:
    raw = (
        result.get("metadata", {})
        if isinstance(result, Mapping)
        else getattr(result, "metadata", {})
    )
    return dict(raw or {}) if isinstance(raw, Mapping) else {}


def _matches_slot_evidence(text: str, slot: PlanningCoverageSlot) -> bool:
    normalized = _normalized_text(text)
    if any(term in normalized for term in slot.evidence_terms):
        return True
    if slot.key == "cig_lots":
        return bool(_CIG_RE.search(text))
    if slot.key == "amounts":
        return bool(_MONEY_RE.search(text))
    if slot.key in {"duration", "deadlines", "sla_penalties"}:
        return bool(_NUMERIC_RE.search(text))
    if slot.key == "platform":
        return bool(_URL_RE.search(text))
    return False


def _result_to_coverage_item(
    result: Any,
    *,
    retriever: str,
    slot: PlanningCoverageSlot,
    coverage_query: str,
    filters: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    text = _result_text(result).strip()
    if not text or not _matches_slot_evidence(text, slot):
        return None

    metadata = _result_metadata(result)
    for key in ("tender_id", "document_id", "doc_type"):
        if key not in metadata and filters and key in filters:
            metadata[key] = filters[key]
    metadata.update(
        {
            "planning_coverage": True,
            "coverage_slot": slot.key,
            "coverage_slot_label": slot.label,
            "coverage_query": coverage_query,
            "coverage_retriever": retriever,
        }
    )
    return {
        "text": text,
        "score": _result_score(result),
        "metadata": metadata,
        "retriever": retriever,
    }


async def run_planning_coverage(
    *,
    query: str,
    config: Mapping[str, Any] | None,
    filters: Mapping[str, Any] | None = None,
    graph_filters: Mapping[str, Any] | None = None,
    sparse_retriever: Any | None = None,
    dense_retriever: Any | None = None,
    graph_retriever: Any | None = None,
) -> PlanningCoverageResult:
    started = time.perf_counter()
    cfg = normalize_planning_coverage_config(config)
    plan = classify_query_for_coverage(query, cfg)
    if not plan.activated:
        return PlanningCoverageResult(
            activated=False,
            query_class=plan.query_class,
            slots_triggered=plan.slots_triggered,
            generated_queries=plan.generated_queries,
            results=[],
            notes=plan.notes,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    retrievers = cfg["retrievers"]
    top_k = int(cfg["topkPerSlot"])
    max_per_slot = int(cfg["maxSourcesPerSlot"])
    global_max = int(cfg["globalMaxCoverageChunks"])
    min_score = float(cfg["minScore"])
    results: list[dict[str, Any]] = []
    per_slot_count: dict[str, int] = {}
    seen: set[tuple[str, str, str]] = set()
    notes = list(plan.notes)

    async def collect(
        raw_results: list[Any],
        *,
        retriever: str,
        slot: PlanningCoverageSlot,
        coverage_query: str,
    ) -> None:
        nonlocal results
        for raw_result in raw_results:
            if len(results) >= global_max:
                return
            if per_slot_count.get(slot.key, 0) >= max_per_slot:
                return
            if _result_score(raw_result) < min_score:
                continue
            item = _result_to_coverage_item(
                raw_result,
                retriever=retriever,
                slot=slot,
                coverage_query=coverage_query,
                filters=filters,
            )
            if item is None:
                continue
            dedup_key = (slot.key, retriever, _normalized_text(item["text"]))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            per_slot_count[slot.key] = per_slot_count.get(slot.key, 0) + 1
            results.append(item)

    for slot_key in plan.slots_triggered:
        slot = PLANNING_COVERAGE_SLOTS[slot_key]
        for coverage_query in plan.generated_queries.get(slot_key, []):
            if len(results) >= global_max:
                break
            if retrievers.get("sparse") and sparse_retriever is not None:
                try:
                    await collect(
                        sparse_retriever.search(
                            query=coverage_query,
                            top_k=top_k,
                            filters=dict(filters or {}) or None,
                        ),
                        retriever="sparse",
                        slot=slot,
                        coverage_query=coverage_query,
                    )
                except Exception as exc:  # pragma: no cover - defensive branch
                    notes.append(
                        _PC_MSGS.error_sparse_retrieval.format(slot=slot.key, error=exc)
                    )
            if retrievers.get("dense") and dense_retriever is not None:
                try:
                    await collect(
                        dense_retriever.search(
                            query=coverage_query,
                            top_k=top_k,
                            filters=dict(filters or {}) or None,
                        ),
                        retriever="dense",
                        slot=slot,
                        coverage_query=coverage_query,
                    )
                except Exception as exc:  # pragma: no cover - defensive branch
                    notes.append(
                        _PC_MSGS.error_dense_retrieval.format(slot=slot.key, error=exc)
                    )
            if retrievers.get("graph") and graph_retriever is not None:
                try:
                    await collect(
                        await graph_retriever.search(
                            query=coverage_query,
                            top_k=top_k,
                            filters=dict(graph_filters or filters or {}) or None,
                        ),
                        retriever="graph",
                        slot=slot,
                        coverage_query=coverage_query,
                    )
                except Exception as exc:  # pragma: no cover - defensive branch
                    notes.append(
                        _PC_MSGS.error_graph_retrieval.format(slot=slot.key, error=exc)
                    )

    return PlanningCoverageResult(
        activated=True,
        query_class=plan.query_class,
        slots_triggered=plan.slots_triggered,
        generated_queries=plan.generated_queries,
        results=results,
        notes=notes,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )
