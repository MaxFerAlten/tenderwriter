"""Deterministic guardrails for procedure-aware tender RAG answers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

BLOCKED_OUTPUT_MESSAGE = "output bloccato: conflitto o dato non verificato"
GUARDRAIL_SETTINGS_KEY = "rag_guardrails"

DEFAULT_GUARDRAIL_CONFIG: dict[str, Any] = {
    "enabled": True,
    "mode": "block",
    "onlyTenderOverview": True,
    "blockOnConflict": True,
    "blockOnUnverifiedNumbers": True,
    "blockOnCrossProcedureMixing": True,
}


class FactStatus(StrEnum):
    VERIFIED = "verificato"
    NOT_DETECTED = "non_rilevato"
    CONFLICT = "conflitto"


ProcedureLabel = str

PROCEDURE_ANCHORS: dict[ProcedureLabel, tuple[str, ...]] = {
    "OSCAT": (
        "gitlab",
        "sonar",
        "nexus",
        "vulnerability assessment",
        "dpa",
        "gpa",
        "gva",
        "sme",
        "mam",
        "sts",
        "devsecops",
        "oscat",
    ),
    "SCT": (
        "cctt",
        "rtpc",
        "presa in carico",
        "fase transitoria",
        "qualificazione acn",
        "tix",
        "via san piero a quaracchi",
        "sistema cloud toscana",
        "sistema cloud toscano",
        "sct",
    ),
}

_CIG_RE = re.compile(r"\bCIG\s*[:\-]?\s*([A-Z0-9]{8,12})\b", re.IGNORECASE)
_PROCEDURE_ID_RE = re.compile(r"\b[0-9]{5,6}/(?:20)?[0-9]{2}\b", re.IGNORECASE)
_PROCEDURE_ID_FIELD_RE = re.compile(
    r"(?P<prefix>\bID\s+procedura\s*:\s*)"
    r"(?P<value>[0-9/\s]{3,30}?)(?=(?:\n\s*[-*])|$|[.;,])",
    re.IGNORECASE,
)
_INCOMPLETE_PROCEDURE_ID_RE = re.compile(
    r"\b(?P<prefix>(?:ID(?:\s+procedura)?|procedura)\s+)"
    r"(?P<value>[0-9]{5,6}/(?:[0-9](?:\s+[0-9]{1,3})+|[0-9]{1,3}(?![0-9])))\b",
    re.IGNORECASE,
)
_DAY_RE = re.compile(r"\b([1-9][0-9]{0,3})\s+giorn[oi]\b", re.IGNORECASE)
_MONTH_RE = re.compile(r"\b([1-9][0-9]{0,2})\s+mesi\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b([1-9][0-9]{0,2})\s+anni\b", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\b([1-9][0-9]?(?:[,.][0-9]+)?|100(?:[,.]0+)?)\s*%", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?:€\s*[\d.]+(?:,\d{2})?|\b(?:euro|eur)\s+[\d.]+(?:,\d{2})?)",
    re.IGNORECASE,
)
_ADDRESS_RE = re.compile(r"\bvia\s+san\s+piero\s+a\s+quaracchi\s+\d+\b", re.IGNORECASE)
_SERVICE_LOCATION_RE = re.compile(
    r"\bluogo\s+di\s+svolgimento\s+del\s+servizio\s+(?:è|e'|e)\s+la\s+"
    r"(Regione\s+[A-Za-zÀ-ÿ' -]+?)(?=\s*(?:\(|[.;,\n]|$))",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")
_SOURCE_BODY_RE = re.compile(
    r"SOURCE_START[^\n]*\n(?P<body>.*?)\nSOURCE_END",
    re.IGNORECASE | re.DOTALL,
)
_SOURCE_PROCEDURE_RE = re.compile(
    r"^SOURCE_START[^\n]*\bprocedure=(?P<label>[A-Za-z_]+)",
    re.IGNORECASE | re.MULTILINE,
)
_PLACEHOLDER_RE = re.compile(
    r"\b(?:entro|fino a|non oltre)\s+giorni\b|"
    r"\bCIG\s*[:\-]?\s*(?!(?:non\s+(?:verificato|rilevato))\b)"
    r"(?:[A-Z0-9]{1,7}\b|(?=$|[,.;:)\]\n]))",
    re.IGNORECASE,
)
_DAY_PLACEHOLDER_RE = re.compile(
    r"\b(?P<prefix>entro|fino a|non oltre)\s+giorni\b",
    re.IGNORECASE,
)
_INCOMPLETE_CIG_RE = re.compile(
    r"\bCIG\s*[:\-]?\s*(?!(?:non\s+(?:verificato|rilevato))\b)"
    r"(?:[A-Z0-9]{1,7}\b|(?=$|[,.;:)\]\n]))",
    re.IGNORECASE,
)
_MASKED_CIG_WITH_VALUE_RE = re.compile(
    r"\bCIG\s+non\s+(?:verificato|rilevato)\s*[:\-]?\s+[A-Z0-9]{8,12}\b",
    re.IGNORECASE,
)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


@dataclass(frozen=True)
class FactSheet:
    procedure_label: ProcedureLabel
    procedure_ids: tuple[str, ...] = ()
    cigs: tuple[str, ...] = ()
    critical_days: tuple[str, ...] = ()
    durations: tuple[str, ...] = ()
    amounts: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    percentages: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    status: FactStatus = FactStatus.NOT_DETECTED

    def protected_values(self) -> set[str]:
        values: set[str] = set()
        for group in (
            self.procedure_ids,
            self.cigs,
            self.critical_days,
            self.durations,
            self.amounts,
            self.locations,
            self.percentages,
        ):
            values.update(group)
        return values

    def protected_numbers(self) -> set[str]:
        numbers: set[str] = set()
        for value in self.protected_values():
            numbers.update(_NUMBER_RE.findall(value))
        return numbers


@dataclass(frozen=True)
class GuardrailValidationResult:
    status: str
    safe_answer: str
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_guardrail_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    incoming = dict(raw or {})
    mode = str(incoming.get("mode", DEFAULT_GUARDRAIL_CONFIG["mode"]))
    return {
        "enabled": bool(incoming.get("enabled", DEFAULT_GUARDRAIL_CONFIG["enabled"])),
        "mode": mode if mode in {"audit", "block"} else "block",
        "onlyTenderOverview": bool(
            incoming.get("onlyTenderOverview", DEFAULT_GUARDRAIL_CONFIG["onlyTenderOverview"])
        ),
        "blockOnConflict": bool(
            incoming.get("blockOnConflict", DEFAULT_GUARDRAIL_CONFIG["blockOnConflict"])
        ),
        "blockOnUnverifiedNumbers": bool(
            incoming.get(
                "blockOnUnverifiedNumbers",
                DEFAULT_GUARDRAIL_CONFIG["blockOnUnverifiedNumbers"],
            )
        ),
        "blockOnCrossProcedureMixing": bool(
            incoming.get(
                "blockOnCrossProcedureMixing",
                DEFAULT_GUARDRAIL_CONFIG["blockOnCrossProcedureMixing"],
            )
        ),
    }


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return tuple(result)


def _canonical_number(value: str) -> str:
    return str(value or "").replace(".", "").replace(",", ".").strip()


def _canonical_token(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def classify_chunk_procedure(text: str) -> ProcedureLabel:
    normalized = _normalize(text)
    scores = {
        label: sum(1 for anchor in anchors if anchor in normalized)
        for label, anchors in PROCEDURE_ANCHORS.items()
    }
    best_label, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "non_attribuibile"
    tied = [label for label, score in scores.items() if score == best_score]
    return best_label if len(tied) == 1 else "non_attribuibile"


def _source_id(item: Mapping[str, Any], index: int) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    chunk_id = metadata.get("chunk_index") or metadata.get("chunk_id") or index
    return f"chunk:{chunk_id}"


def _extract_all(pattern: re.Pattern[str], text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in pattern.finditer(text):
        value = match.group(1) if match.groups() else match.group(0)
        values.append(value)
    return _unique(values)


def _extract_day_values(text: str) -> tuple[str, ...]:
    return _unique([f"{value} giorni" for value in _extract_all(_DAY_RE, text)])


def _extract_duration_values(text: str) -> tuple[str, ...]:
    values = [f"{value} mesi" for value in _extract_all(_MONTH_RE, text)]
    values.extend(f"{value} anni" for value in _extract_all(_YEAR_RE, text))
    return _unique(values)


def _extract_percentage_values(text: str) -> tuple[str, ...]:
    return _unique([f"{value}%" for value in _extract_all(_PERCENT_RE, text)])


def _extract_location_values(text: str) -> tuple[str, ...]:
    values = [*_extract_all(_ADDRESS_RE, text), *_extract_all(_SERVICE_LOCATION_RE, text)]
    return _unique(values)


def _has_extractable_protected_fact(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            _CIG_RE,
            _PROCEDURE_ID_RE,
            _DAY_RE,
            _MONTH_RE,
            _YEAR_RE,
            _PERCENT_RE,
            _MONEY_RE,
            _ADDRESS_RE,
            _SERVICE_LOCATION_RE,
        )
    )


def _metadata_link_values(item: Mapping[str, Any]) -> set[tuple[str, str]]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    values: set[tuple[str, str]] = set()

    tender_id = metadata.get("tender_id")
    document_id = metadata.get("document_id")
    if tender_id not in (None, "") and document_id not in (None, ""):
        values.add(("tender_document", f"{tender_id}:{document_id}"))

    for key in (
        "source_document_ref",
        "source_file",
        "tender_id",
        "document_id",
    ):
        value = metadata.get(key)
        if value in (None, ""):
            continue
        values.add((key, str(value)))
    return values


def _detect_conflicts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    return (field_name,) if len(values) > 1 else ()


def build_fact_sheet(
    context_items: Sequence[Mapping[str, Any]],
    *,
    query: str,
) -> FactSheet:
    labels = [
        label
        for item in context_items
        if (label := classify_chunk_procedure(str(item.get("text") or ""))) != "non_attribuibile"
    ]
    query_label = classify_chunk_procedure(query)
    if query_label != "non_attribuibile":
        labels.insert(0, query_label)

    procedure_label = _unique(labels)[0] if labels else "non_attribuibile"
    source_ids: list[str] = []
    procedure_ids: list[str] = []
    cigs: list[str] = []
    critical_days: list[str] = []
    durations: list[str] = []
    amounts: list[str] = []
    locations: list[str] = []
    percentages: list[str] = []

    extraction_items: list[tuple[int, Mapping[str, Any]]] = []
    procedure_link_values: set[tuple[str, str]] = set()
    if procedure_label in PROCEDURE_ANCHORS:
        for item in context_items:
            if classify_chunk_procedure(str(item.get("text") or "")) == procedure_label:
                procedure_link_values.update(_metadata_link_values(item))

    for index, item in enumerate(context_items):
        text = str(item.get("text") or "")
        if not text:
            continue
        item_label = classify_chunk_procedure(text)
        if (
            procedure_label in PROCEDURE_ANCHORS
            and item_label != procedure_label
            and not (
                item_label == "non_attribuibile"
                and _has_extractable_protected_fact(text)
                and bool(procedure_link_values & _metadata_link_values(item))
            )
        ):
            continue
        extraction_items.append((index, item))

    for index, item in extraction_items:
        text = str(item.get("text") or "")
        source_ids.append(_source_id(item, index))
        procedure_ids.extend(_extract_all(_PROCEDURE_ID_RE, text))
        cigs.extend(_extract_all(_CIG_RE, text))
        critical_days.extend(_extract_day_values(text))
        durations.extend(_extract_duration_values(text))
        amounts.extend(_extract_all(_MONEY_RE, text))
        locations.extend(_extract_location_values(text))
        percentages.extend(_extract_percentage_values(text))

    normalized_procedure_ids = _unique(procedure_ids)
    normalized_cigs = _unique(cigs)
    normalized_days = _unique(critical_days)
    normalized_durations = _unique(durations)
    normalized_amounts = _unique(amounts)
    normalized_locations = _unique(locations)
    normalized_percentages = _unique(percentages)
    conflicts = (
        *_detect_conflicts(normalized_cigs, "cig"),
        *_detect_conflicts(normalized_procedure_ids, "procedure_id"),
    )
    has_values = any(
        (
            normalized_procedure_ids,
            normalized_cigs,
            normalized_days,
            normalized_durations,
            normalized_amounts,
            normalized_locations,
            normalized_percentages,
        )
    )
    status = (
        FactStatus.CONFLICT
        if conflicts
        else FactStatus.VERIFIED
        if has_values
        else FactStatus.NOT_DETECTED
    )

    return FactSheet(
        procedure_label=procedure_label,
        procedure_ids=normalized_procedure_ids,
        cigs=normalized_cigs,
        critical_days=normalized_days,
        durations=normalized_durations,
        amounts=normalized_amounts,
        locations=normalized_locations,
        percentages=normalized_percentages,
        source_ids=_unique(source_ids),
        conflicts=tuple(conflicts),
        status=status,
    )


def _answer_procedure_labels(answer: str) -> set[ProcedureLabel]:
    normalized = _normalize(answer)
    return {
        label
        for label, anchors in PROCEDURE_ANCHORS.items()
        if any(anchor in normalized for anchor in anchors)
    }


def _allows_comparison(text: str) -> bool:
    normalized = _normalize(text)
    return any(term in normalized for term in ("confront", "compar", "distingu", "separ"))


def _duplicate_paragraph_failures(answer: str) -> tuple[str, ...]:
    seen: set[str] = set()
    for block in _PARAGRAPH_SPLIT_RE.split(str(answer or "").strip()):
        normalized = _normalize(block)
        if not normalized or len(normalized) < 80:
            continue
        if normalized in seen:
            return ("duplicate_paragraph",)
        seen.add(normalized)
    return ()


def _unverified_cig_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    allowed = {_canonical_token(value) for value in fact_sheet.cigs}
    failures = [
        f"unverified_cig:{value}"
        for value in _extract_all(_CIG_RE, answer)
        if _canonical_token(value) not in allowed
    ]
    return tuple(failures)


def _unverified_procedure_id_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    allowed_exact = {value.strip() for value in fact_sheet.procedure_ids}
    allowed = {_canonical_token(value) for value in fact_sheet.procedure_ids}
    failures = [
        f"unverified_procedure_id:{value}"
        for value in _extract_all(_PROCEDURE_ID_RE, answer)
        if _canonical_token(value) not in allowed
    ]
    for match in _PROCEDURE_ID_FIELD_RE.finditer(answer or ""):
        raw_value = match.group("value").strip()
        value = re.sub(r"\s+", "", match.group("value")).strip()
        if value and (value not in allowed_exact or raw_value != value):
            failures.append(f"malformed_procedure_id:{value[:40]}")
    for match in _INCOMPLETE_PROCEDURE_ID_RE.finditer(answer or ""):
        raw_value = match.group("value")
        value = re.sub(r"\s+", "", raw_value).strip()
        if _canonical_token(value) not in allowed or raw_value != value:
            failures.append(f"incomplete_procedure_id:{value}")
    return tuple(failures)


def _unverified_pattern_failures(
    *,
    answer: str,
    pattern: re.Pattern[str],
    allowed_values: Sequence[str],
    suffix: str,
    failure_prefix: str,
) -> tuple[str, ...]:
    allowed_numbers = {
        _canonical_number(number)
        for value in allowed_values
        for number in _NUMBER_RE.findall(value)
    }
    failures: list[str] = []
    for value in _extract_all(pattern, answer):
        if _canonical_number(value) not in allowed_numbers:
            failures.append(f"{failure_prefix}:{value}{suffix}")
    return tuple(failures)


def _unverified_amount_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    allowed = {_canonical_token(value) for value in fact_sheet.amounts}
    failures = [
        f"unverified_amount:{value}"
        for value in _extract_all(_MONEY_RE, answer)
        if _canonical_token(value) not in allowed
    ]
    return tuple(failures)


def _unverified_location_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    allowed = {_canonical_token(value) for value in fact_sheet.locations}
    failures = [
        f"unverified_location:{value}"
        for value in _extract_all(_ADDRESS_RE, answer)
        if _canonical_token(value) not in allowed
    ]
    return tuple(failures)


def _unverified_protected_fact_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    failures: list[str] = []
    failures.extend(_unverified_cig_failures(answer, fact_sheet))
    failures.extend(_unverified_procedure_id_failures(answer, fact_sheet))
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_DAY_RE,
            allowed_values=fact_sheet.critical_days,
            suffix="",
            failure_prefix="unverified_number",
        )
    )
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_MONTH_RE,
            allowed_values=fact_sheet.durations,
            suffix=" mesi",
            failure_prefix="unverified_duration",
        )
    )
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_YEAR_RE,
            allowed_values=fact_sheet.durations,
            suffix=" anni",
            failure_prefix="unverified_duration",
        )
    )
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_PERCENT_RE,
            allowed_values=fact_sheet.percentages,
            suffix="%",
            failure_prefix="unverified_percentage",
        )
    )
    failures.extend(_unverified_amount_failures(answer, fact_sheet))
    failures.extend(_unverified_location_failures(answer, fact_sheet))
    return _unique(failures)


def _replace_unverified_cigs(answer: str, fact_sheet: FactSheet) -> str:
    allowed = {_canonical_token(value) for value in fact_sheet.cigs}

    def replacement(match: re.Match[str]) -> str:
        value = match.group(1)
        if _canonical_token(value) in allowed and "cig" not in fact_sheet.conflicts:
            return match.group(0)
        return "CIG non verificato"

    return _CIG_RE.sub(replacement, answer)


def _replace_unverified_procedure_ids(answer: str, fact_sheet: FactSheet) -> str:
    allowed = {_canonical_token(value) for value in fact_sheet.procedure_ids}
    allowed_exact = {value.strip() for value in fact_sheet.procedure_ids}

    def field_replacement(match: re.Match[str]) -> str:
        raw_value = match.group("value").strip()
        value = re.sub(r"\s+", "", match.group("value")).strip()
        if (
            value in allowed_exact
            and raw_value == value
            and "procedure_id" not in fact_sheet.conflicts
        ):
            return match.group(0)
        if len(fact_sheet.procedure_ids) == 1 and "procedure_id" not in fact_sheet.conflicts:
            return f"{match.group('prefix')}{fact_sheet.procedure_ids[0]}"
        return f"{match.group('prefix')}ID procedura non verificato"

    def incomplete_replacement(match: re.Match[str]) -> str:
        raw_value = match.group("value")
        value = re.sub(r"\s+", "", raw_value).strip()
        if (
            _canonical_token(value) in allowed
            and raw_value == value
            and "procedure_id" not in fact_sheet.conflicts
        ):
            return match.group(0)
        if len(fact_sheet.procedure_ids) == 1 and "procedure_id" not in fact_sheet.conflicts:
            return f"{match.group('prefix')}{fact_sheet.procedure_ids[0]}"
        return f"{match.group('prefix')}ID procedura non verificato"

    def replacement(match: re.Match[str]) -> str:
        value = match.group(0)
        if _canonical_token(value) in allowed and "procedure_id" not in fact_sheet.conflicts:
            return value
        return "ID procedura non verificato"

    repaired = _PROCEDURE_ID_FIELD_RE.sub(field_replacement, answer)
    repaired = _INCOMPLETE_PROCEDURE_ID_RE.sub(incomplete_replacement, repaired)
    return _PROCEDURE_ID_RE.sub(replacement, repaired)


def _replace_unverified_pattern_values(
    answer: str,
    *,
    pattern: re.Pattern[str],
    allowed_values: Sequence[str],
    replacement_text: str,
) -> str:
    allowed_numbers = {
        _canonical_number(number)
        for value in allowed_values
        for number in _NUMBER_RE.findall(value)
    }

    def replacement(match: re.Match[str]) -> str:
        value = match.group(1) if match.groups() else match.group(0)
        if _canonical_number(value) in allowed_numbers:
            return match.group(0)
        return replacement_text

    return pattern.sub(replacement, answer)


def _replace_unverified_token_values(
    answer: str,
    *,
    pattern: re.Pattern[str],
    allowed_values: Sequence[str],
    replacement_text: str,
) -> str:
    allowed = {_canonical_token(value) for value in allowed_values}

    def replacement(match: re.Match[str]) -> str:
        value = match.group(1) if match.groups() else match.group(0)
        if _canonical_token(value) in allowed:
            return match.group(0)
        return replacement_text

    return pattern.sub(replacement, answer)


def _replace_numeric_placeholders(answer: str) -> str:
    repaired = _DAY_PLACEHOLDER_RE.sub(
        lambda match: f"{match.group('prefix')} termine non verificato",
        answer,
    )
    repaired = _INCOMPLETE_CIG_RE.sub("CIG non verificato", repaired)
    return _MASKED_CIG_WITH_VALUE_RE.sub("CIG non verificato", repaired)


def repair_unsupported_protected_facts(answer: str, fact_sheet: FactSheet) -> str:
    """Mask unsupported protected facts while preserving the rest of the answer."""

    repaired = str(answer or "")
    repaired = _replace_numeric_placeholders(repaired)
    repaired = _replace_unverified_cigs(repaired, fact_sheet)
    repaired = _replace_unverified_procedure_ids(repaired, fact_sheet)
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_DAY_RE,
        allowed_values=fact_sheet.critical_days,
        replacement_text="giorni non verificati",
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_MONTH_RE,
        allowed_values=fact_sheet.durations,
        replacement_text="durata non verificata",
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_YEAR_RE,
        allowed_values=fact_sheet.durations,
        replacement_text="durata non verificata",
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_PERCENT_RE,
        allowed_values=fact_sheet.percentages,
        replacement_text="percentuale non verificata",
    )
    repaired = _replace_unverified_token_values(
        repaired,
        pattern=_MONEY_RE,
        allowed_values=fact_sheet.amounts,
        replacement_text="importo non verificato",
    )
    repaired = _replace_unverified_token_values(
        repaired,
        pattern=_ADDRESS_RE,
        allowed_values=fact_sheet.locations,
        replacement_text="sede non verificata",
    )
    return repaired


def guardrail_issue_snippets(answer: str, *, limit: int = 6) -> tuple[str, ...]:
    """Return short protected-fact snippets that explain guardrail blocks."""

    snippets: list[str] = []
    for label, pattern in (
        ("placeholder", _PLACEHOLDER_RE),
        ("masked_cig_value", _MASKED_CIG_WITH_VALUE_RE),
        ("cig", _CIG_RE),
        ("procedure_id_field", _PROCEDURE_ID_FIELD_RE),
        ("incomplete_procedure_id", _INCOMPLETE_PROCEDURE_ID_RE),
        ("procedure_id", _PROCEDURE_ID_RE),
        ("day", _DAY_RE),
        ("month", _MONTH_RE),
        ("year", _YEAR_RE),
        ("percent", _PERCENT_RE),
        ("money", _MONEY_RE),
        ("address", _ADDRESS_RE),
    ):
        for match in pattern.finditer(answer or ""):
            snippet = " ".join(match.group(0).split())
            snippets.append(f"{label}:{snippet[:80]}")
            if len(snippets) >= limit:
                return tuple(snippets)
    return tuple(snippets)


def _conflicted_protected_fact_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    conflicts = set(fact_sheet.conflicts)
    if not conflicts:
        return ("fact_sheet_conflict",) if fact_sheet.status == FactStatus.CONFLICT else ()

    failures: list[str] = []
    if "cig" in conflicts and _extract_all(_CIG_RE, answer):
        failures.append("fact_sheet_conflict")
    if "procedure_id" in conflicts and _extract_all(_PROCEDURE_ID_RE, answer):
        failures.append("fact_sheet_conflict")

    unknown_conflicts = conflicts - {"cig", "procedure_id"}
    if unknown_conflicts:
        failures.append("fact_sheet_conflict")

    return _unique(failures)


def fact_sheet_from_guarded_context(context: str) -> FactSheet | None:
    match = re.search(r"FACT_SHEET_START\n(?P<body>.*?)\nFACT_SHEET_END", context, re.DOTALL)
    if not match:
        return None
    body = match.group("body")
    values: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()

    def split_values(key: str, prefix: str = "") -> tuple[str, ...]:
        raw = values.get(key, "")
        if raw in {"", "non_rilevato", "nessuno"}:
            return ()
        parts = tuple(part.strip() for part in raw.split(", ") if part.strip())
        if prefix:
            return tuple(part.removeprefix(prefix).strip() for part in parts)
        return parts

    status_value = values.get("stato_verifica", FactStatus.NOT_DETECTED.value)
    try:
        status = FactStatus(status_value)
    except ValueError:
        status = FactStatus.NOT_DETECTED
    return FactSheet(
        procedure_label=values.get("procedura", "non_attribuibile"),
        procedure_ids=split_values("procedure_id"),
        cigs=split_values("cig", "CIG "),
        critical_days=split_values("giorni_critici"),
        durations=split_values("durata"),
        amounts=split_values("importi"),
        locations=split_values("sedi_luoghi"),
        percentages=split_values("percentuali"),
        source_ids=split_values("fonti"),
        conflicts=split_values("conflitti"),
        status=status,
    )


def context_items_from_guarded_context(context: str) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    for index, match in enumerate(_SOURCE_BODY_RE.finditer(context or "")):
        items.append({"text": match.group("body"), "metadata": {"chunk_index": index}})
    return tuple(items)


def source_procedure_labels_from_guarded_context(context: str) -> tuple[ProcedureLabel, ...]:
    labels: list[str] = []
    for match in _SOURCE_PROCEDURE_RE.finditer(context or ""):
        label = match.group("label").upper()
        if label in PROCEDURE_ANCHORS:
            labels.append(label)
    return _unique(labels)


def validate_guarded_answer(
    *,
    answer: str,
    fact_sheet: FactSheet,
    guarded: bool,
    query: str = "",
    config: Mapping[str, Any] | None = None,
    allowed_procedure_labels: Sequence[ProcedureLabel] | None = None,
) -> GuardrailValidationResult:
    cfg = normalize_guardrail_config(config)
    if not guarded or not cfg["enabled"]:
        return GuardrailValidationResult(status="PASS", safe_answer=answer)

    failures: list[str] = []
    if cfg["blockOnConflict"] and fact_sheet.status == FactStatus.CONFLICT:
        failures.extend(_conflicted_protected_fact_failures(answer, fact_sheet))
    if _PLACEHOLDER_RE.search(answer):
        failures.append("numeric_placeholder")
    if _MASKED_CIG_WITH_VALUE_RE.search(answer):
        failures.append("masked_cig_value")
    failures.extend(_duplicate_paragraph_failures(answer))
    if cfg["blockOnUnverifiedNumbers"]:
        failures.extend(_unverified_protected_fact_failures(answer, fact_sheet))

    labels = _answer_procedure_labels(answer)
    comparison_allowed = _allows_comparison(answer) or _allows_comparison(query)
    allowed_labels = {
        label
        for label in (*tuple(allowed_procedure_labels or ()), fact_sheet.procedure_label)
        if label in PROCEDURE_ANCHORS
    }
    if cfg["blockOnCrossProcedureMixing"]:
        unsupported_labels = labels - allowed_labels
        if len(labels) > 1 and unsupported_labels and not comparison_allowed:
            failures.append("cross_procedure_mixing")
        if fact_sheet.procedure_label in {"OSCAT", "SCT"}:
            other_labels = (labels - {fact_sheet.procedure_label}) - allowed_labels
            if other_labels and not comparison_allowed:
                failures.append("wrong_procedure_label")

    if failures:
        status = "BLOCK" if cfg["mode"] == "block" else "AUDIT"
        return GuardrailValidationResult(
            status=status,
            safe_answer=BLOCKED_OUTPUT_MESSAGE if status == "BLOCK" else answer,
            failures=_unique(failures),
        )
    return GuardrailValidationResult(status="PASS", safe_answer=answer)
