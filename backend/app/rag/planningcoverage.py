"""Tender-specific planning coverage retrieval helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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


TENDER_QUERY_TERMS = (
    "gara",
    "appalto",
    "procedura",
    "disciplinare",
    "capitolato",
    "lotto",
    "lotti",
    "cig",
    "rup",
    "offerta",
    "stazione appaltante",
)

PLANNING_COVERAGE_SLOTS: dict[str, PlanningCoverageSlot] = {
    "identification": PlanningCoverageSlot(
        key="identification",
        label="Identificazione procedura",
        trigger_terms=("determina", "determinazione", "rup", "stazione appaltante", "procedura"),
        queries=(
            '"determinazione" "rep." "prot." "indice" "indetta"',
            '"responsabile unico del progetto" "RUP" "ing." "dott."',
            '"stazione appaltante" "procedura" "numero gara"',
        ),
        evidence_terms=(
            "determinazione",
            "responsabile unico",
            "rup",
            "stazione appaltante",
            "indetta",
            "rep.",
            "prot.",
        ),
    ),
    "cig_lots": PlanningCoverageSlot(
        key="cig_lots",
        label="CIG e lotti",
        trigger_terms=("cig", "lotto", "lotti", "simog"),
        queries=(
            '"CIG" "lotto 1" "lotto 2" "lotto 3" "lotto 4"',
            '"codice CIG" "lotto" "gara"',
            '"SIMOG" "CIG" "lotti"',
        ),
        evidence_terms=("cig", "lotto", "lotti", "simog"),
    ),
    "amounts": PlanningCoverageSlot(
        key="amounts",
        label="Importi e massimali",
        trigger_terms=(
            "importo",
            "base d'asta",
            "base asta",
            "valore",
            "euro",
            "oneri",
            "massimale",
        ),
        queries=(
            '"base d\'asta" "IVA esclusa" "importo" "€"',
            '"massimale" "accordo quadro" "quinto d\'obbligo" "20%"',
            '"oneri sicurezza" "importo" "euro"',
        ),
        evidence_terms=(
            "base d'asta",
            "base asta",
            "iva esclusa",
            "importo",
            "euro",
            "€",
            "massimale",
            "oneri",
            "quinto",
        ),
    ),
    "duration": PlanningCoverageSlot(
        key="duration",
        label="Durata",
        trigger_terms=("durata", "mesi", "giorni", "proroga", "decorrenza", "stipula"),
        queries=(
            '"durata" "36 mesi" "mesi dalla stipula" "proroga"',
            '"decorrenza" "contratti attuativi" "mesi"',
        ),
        evidence_terms=("durata", "mesi", "giorni", "proroga", "decorrenza", "stipula"),
    ),
    "deadlines": PlanningCoverageSlot(
        key="deadlines",
        label="Scadenze",
        trigger_terms=("scadenza", "termine", "presentazione", "offerte", "ore", "deadline"),
        queries=(
            '"termine" "presentazione" "offerte" "ore"',
            '"scadenza" "presentazione offerte" "data"',
        ),
        evidence_terms=("termine", "presentazione", "offerte", "ore", "scadenza", "deadline"),
    ),
    "platform": PlanningCoverageSlot(
        key="platform",
        label="Piattaforma e accesso",
        trigger_terms=(
            "piattaforma",
            "sardegnacat",
            "start",
            "sintel",
            "mepa",
            "spid",
            "cie",
            "cns",
            "url",
        ),
        queries=(
            '"https://" "sardegnacat" "URL" "piattaforma"',
            '"SPID" "CIE" "CNS" "eIDAS" "autenticazione"',
            '"portale" "piattaforma telematica" "gara"',
        ),
        evidence_terms=(
            "https://",
            "piattaforma",
            "sardegnacat",
            "start",
            "sintel",
            "mepa",
            "spid",
            "cie",
            "cns",
            "eidas",
        ),
    ),
    "scoring": PlanningCoverageSlot(
        key="scoring",
        label="Punteggi e criteri",
        trigger_terms=(
            "punteggio",
            "offerta tecnica",
            "offerta economica",
            "criterio",
            "valutazione",
        ),
        queries=(
            '"punteggio" "offerta tecnica" "offerta economica" "70" "80"',
            '"criteri di valutazione" "punteggio tecnico" "punteggio economico"',
        ),
        evidence_terms=(
            "punteggio",
            "offerta tecnica",
            "offerta economica",
            "criteri",
            "valutazione",
        ),
    ),
    "certifications": PlanningCoverageSlot(
        key="certifications",
        label="Certificazioni",
        trigger_terms=(
            "certificazione",
            "certificazioni",
            "iso",
            "acn",
            "qualificazione",
            "uni/pdr",
        ),
        queries=(
            '"ISO/IEC 27001" "ISO/IEC 27017" "ISO/IEC 27018" "punti"',
            '"UNI/PdR 125:2022" "SA 8000" "ISO 26000"',
            '"qualificazione ACN" "certificazione" "obbligatoria"',
        ),
        evidence_terms=(
            "iso/iec",
            "iso ",
            "uni/pdr",
            "sa 8000",
            "acn",
            "certificazione",
            "qualificazione",
        ),
    ),
    "sla_penalties": PlanningCoverageSlot(
        key="sla_penalties",
        label="SLA e penali",
        trigger_terms=(
            "sla",
            "penale",
            "penali",
            "livello di servizio",
            "disponibilita",
            "disponibilità",
        ),
        queries=(
            '"penale" "%" "livello di servizio" "SLA" "disponibilità"',
            '"penali" "livelli di servizio" "risoluzione"',
        ),
        evidence_terms=(
            "sla",
            "penale",
            "penali",
            "livello di servizio",
            "disponibilità",
            "risoluzione",
        ),
    ),
    "documents": PlanningCoverageSlot(
        key="documents",
        label="Documenti e vincoli",
        trigger_terms=(
            "passoe",
            "avcpass",
            "dgue",
            "garanzia",
            "cauzione",
            "documenti",
            "vincolo",
        ),
        queries=(
            '"PASSOE" "AVCpass" "DGUE" "garanzia" "cauzione"',
            '"max" "lotti" "aggiudicabili" "partecipare" "vincolo"',
            '"documentazione amministrativa" "disciplinare" "allegati"',
        ),
        evidence_terms=(
            "passoe",
            "avcpass",
            "dgue",
            "garanzia",
            "cauzione",
            "vincolo",
            "allegati",
        ),
    ),
}

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
    return any(term in normalized for term in TENDER_QUERY_TERMS)


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
            notes=["Planning coverage disabilitato da configurazione."],
        )

    if cfg["onlyTenderQueries"] and not tender_like:
        return PlanningCoveragePlan(
            query_class="generic",
            activated=False,
            slots_triggered=[],
            generated_queries={},
            notes=["Query non classificata come gara; coverage non eseguito."],
        )

    enabled_slots = [
        slot
        for key, slot in PLANNING_COVERAGE_SLOTS.items()
        if cfg["slots"].get(key, False)
    ]
    run_all_enabled = cfg["mode"] == "always_on" or (cfg["alwaysRunPlanner"] and tender_like)
    selected_slots = (
        enabled_slots
        if run_all_enabled
        else [slot for slot in enabled_slots if _slot_triggered_by_query(slot, normalized_query)]
    )

    generated_queries = {slot.key: list(slot.queries) for slot in selected_slots}
    notes = [
        "Coverage planner attivato su query tender-like."
        if tender_like
        else "Coverage planner attivato da configurazione always_on."
    ]
    if not selected_slots:
        notes.append("Nessuno slot specifico attivato.")

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
        result.get("score", 0.0)
        if isinstance(result, Mapping)
        else getattr(result, "score", 0.0)
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
                    notes.append(f"Sparse retrieval fallito per slot {slot.key}: {exc}")
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
                    notes.append(f"Dense retrieval fallito per slot {slot.key}: {exc}")
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
                    notes.append(f"Graph retrieval fallito per slot {slot.key}: {exc}")

    return PlanningCoverageResult(
        activated=True,
        query_class=plan.query_class,
        slots_triggered=plan.slots_triggered,
        generated_queries=plan.generated_queries,
        results=results,
        notes=notes,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )
