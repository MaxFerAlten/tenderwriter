"""Deterministic guardrails for procedure-aware tender RAG answers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.rag.internal_prompting import default_language
from app.rag.localization import (
    EngineMessages,
    GuardrailLexicon,
    GuardrailPatterns,
    GuardrailRepairMessages,
    get_engine_messages,
    get_guardrail_lexicon,
    get_guardrail_patterns,
    get_guardrail_repair_messages,
)

if TYPE_CHECKING:
    from app.rag.procedure_profiles import ProcedureProfile

_GUARDRAIL_LEXICON: GuardrailLexicon = get_guardrail_lexicon(default_language())
_GUARDRAIL_PATTERNS: GuardrailPatterns = get_guardrail_patterns(default_language())
BLOCKED_OUTPUT_MESSAGE = get_guardrail_repair_messages(default_language()).blocked_output
GUARDRAIL_SETTINGS_KEY = "rag_guardrails"


def _repair_messages(language: str | None = None) -> GuardrailRepairMessages:
    return get_guardrail_repair_messages(language)


def _engine_messages(language: str | None = None) -> EngineMessages:
    return get_engine_messages(language)

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

PROCEDURE_ANCHORS: dict[ProcedureLabel, tuple[str, ...]] = dict(
    _GUARDRAIL_LEXICON.procedure_anchors
)

# --- Locale-invariant patterns (no language tokens) stay inline. ---
_CIG_RE = re.compile(r"\bCIG\s*[:\-]?\s*([A-Z0-9]{8,12})\b", re.IGNORECASE)
_PROCEDURE_ID_RE = re.compile(r"\b[0-9]{5,6}/(?:20)?[0-9]{2}\b", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\b([1-9][0-9]?(?:[,.][0-9]+)?|100(?:[,.]0+)?)\s*%", re.IGNORECASE)
_MONEY_NUMBER_PATTERN = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:[,.]\d{2})?"
_MONEY_NUMBER_VALUE_RE = re.compile(_MONEY_NUMBER_PATTERN)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")
_SOURCE_BODY_RE = re.compile(
    r"SOURCE_START[^\n]*\n(?P<body>.*?)\nSOURCE_END",
    re.IGNORECASE | re.DOTALL,
)
_SOURCE_PROCEDURE_RE = re.compile(
    r"^SOURCE_START[^\n]*\bprocedure=(?P<label>[A-Za-z_]+)",
    re.IGNORECASE | re.MULTILINE,
)
_CONTAMINATION_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])")
_CORRUPT_MONEY_ARTIFACT_RE = re.compile(
    r"(?<![\d.,])"
    r"(?:"
    # mixed decimal+dot+slash artifacts: 1.573.025,20.0//25,20 etc.
    r"\d{1,3}(?:\.\d{3})*,\d{1,3}\.\d+(?:[/_]+\d+(?:[,.]\d+)?)*|"
    # money number followed by stray /_ + number: 25.20_25,20
    r"\d{1,3}(?:\.\d{3})*[,.]\d+[/_]+\d+(?:[,.]\d+)?"
    r")",
)
_FALSE_MISSING_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")

# --- Locale-bound patterns: skeletons + Italian tokens compiled from the
# guardrail-patterns asset by localization.get_guardrail_patterns. ---
_PROCEDURE_ID_FIELD_RE = _GUARDRAIL_PATTERNS.procedure_id_field
_INCOMPLETE_PROCEDURE_ID_RE = _GUARDRAIL_PATTERNS.incomplete_procedure_id
_DAY_RE = _GUARDRAIL_PATTERNS.day
_MONTH_RE = _GUARDRAIL_PATTERNS.month
_YEAR_RE = _GUARDRAIL_PATTERNS.year
_MONEY_RE = _GUARDRAIL_PATTERNS.money
_MONEY_MILLION_RE = _GUARDRAIL_PATTERNS.money_million
_ADDRESS_RE = _GUARDRAIL_PATTERNS.address
_SERVICE_LOCATION_RE = _GUARDRAIL_PATTERNS.service_location
_PLACEHOLDER_RE = _GUARDRAIL_PATTERNS.placeholder
_DAY_PLACEHOLDER_RE = _GUARDRAIL_PATTERNS.day_placeholder
_INCOMPLETE_CIG_RE = _GUARDRAIL_PATTERNS.incomplete_cig
_MASKED_CIG_WITH_VALUE_RE = _GUARDRAIL_PATTERNS.masked_cig_with_value
_INLINE_UNVERIFIED_PROCEDURE_ID_RE = _GUARDRAIL_PATTERNS.inline_unverified_procedure_id
_INLINE_UNVERIFIED_CIG_RE = _GUARDRAIL_PATTERNS.inline_unverified_cig
OSCAT_SCT_CONTAMINATION_RE = _GUARDRAIL_PATTERNS.oscat_sct_contamination
OSCAT_IDENTITY_KEYWORD_RE = _GUARDRAIL_PATTERNS.oscat_identity_keyword
_MALFORMED_ARTICLE_RE = _GUARDRAIL_PATTERNS.malformed_article
_DURATION_RANGE_RE = _GUARDRAIL_PATTERNS.duration_range
_CIVIL_ARTICLE_THOUSAND_SEP_RE = _GUARDRAIL_PATTERNS.civil_article_thousand_sep
_MONEY_RANGE_NARRATIVE_RE = _GUARDRAIL_PATTERNS.money_range_narrative
_FALSE_MISSING_MARKER_RE = _GUARDRAIL_PATTERNS.false_missing_marker
_PROCEDURE_ID_FALSE_MISSING_RE = _GUARDRAIL_PATTERNS.procedure_id_false_missing
_FALSE_MISSING_FIELD_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    _GUARDRAIL_PATTERNS.false_missing_field_res
)


def contamination_re_for(
    profiles: tuple[ProcedureProfile, ...] | None,
) -> re.Pattern[str]:
    """Contamination regex with the active profiles' markers overlaid on base."""
    from app.rag.localization import get_guardrail_patterns

    return get_guardrail_patterns(
        default_language(), profiles=tuple(profiles or ())
    ).oscat_sct_contamination


def identity_re_for(
    profiles: tuple[ProcedureProfile, ...] | None,
) -> re.Pattern[str]:
    """Identity-marker regex with the active profiles overlaid on base."""
    from app.rag.localization import get_guardrail_patterns

    return get_guardrail_patterns(
        default_language(), profiles=tuple(profiles or ())
    ).oscat_identity_keyword


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


def _decimal_from_money_number(value: str) -> Decimal | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        normalized = raw.replace(".", "")
    else:
        normalized = raw
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _canonical_money_value(value: str) -> str:
    match = _MONEY_NUMBER_VALUE_RE.search(str(value or ""))
    if not match:
        return _canonical_token(value)

    amount = _decimal_from_money_number(match.group(0))
    if amount is None:
        return _canonical_token(value)
    if _MONEY_MILLION_RE.search(value or ""):
        amount *= Decimal("1000000")
    with suppress(InvalidOperation):
        amount = amount.quantize(Decimal("0.01"))
    return format(amount, "f")


def classify_chunk_procedure(
    text: str,
    *,
    active_profiles: tuple[ProcedureProfile, ...] | None = None,
) -> ProcedureLabel:
    from app.rag.procedure_profiles import active_procedure_anchors

    anchors_by_label = dict(PROCEDURE_ANCHORS)
    if active_profiles:
        for label, anchors in active_procedure_anchors(active_profiles).items():
            anchors_by_label[label] = (*anchors_by_label.get(label, ()), *anchors)
    if not anchors_by_label:
        return _engine_messages().procedure_label_unattributed
    normalized = _normalize(text)
    scores = {
        label: sum(1 for anchor in anchors if anchor in normalized)
        for label, anchors in anchors_by_label.items()
    }
    best_label, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return _engine_messages().procedure_label_unattributed
    tied = [label for label, score in scores.items() if score == best_score]
    return best_label if len(tied) == 1 else _engine_messages().procedure_label_unattributed


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
    unit = _repair_messages().unit_days
    return _unique([f"{value} {unit}" for value in _extract_all(_DAY_RE, text)])


def _extract_duration_values(text: str) -> tuple[str, ...]:
    messages = _repair_messages()
    values = [
        f"{value} {messages.unit_months}" for value in _extract_all(_MONTH_RE, text)
    ]
    values.extend(
        f"{value} {messages.unit_years}" for value in _extract_all(_YEAR_RE, text)
    )
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
    active_profiles: tuple[ProcedureProfile, ...] | None = None,
) -> FactSheet:
    unattributed = _engine_messages().procedure_label_unattributed
    labels = [
        label
        for item in context_items
        if (
            label := classify_chunk_procedure(
                str(item.get("text") or ""), active_profiles=active_profiles
            )
        )
        != unattributed
    ]
    query_label = classify_chunk_procedure(query, active_profiles=active_profiles)
    if query_label != unattributed:
        labels.insert(0, query_label)

    procedure_label = _unique(labels)[0] if labels else unattributed
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
            if (
                classify_chunk_procedure(
                    str(item.get("text") or ""), active_profiles=active_profiles
                )
                == procedure_label
            ):
                procedure_link_values.update(_metadata_link_values(item))

    for index, item in enumerate(context_items):
        text = str(item.get("text") or "")
        if not text:
            continue
        item_label = classify_chunk_procedure(text, active_profiles=active_profiles)
        if (
            procedure_label in PROCEDURE_ANCHORS
            and item_label != procedure_label
            and not (
                item_label == unattributed
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
    return any(
        term in normalized for term in _GUARDRAIL_LEXICON.comparison_markers
    )


_SEMANTIC_THEME_KEYWORDS: dict[str, frozenset[str]] = (
    _GUARDRAIL_LEXICON.semantic_theme_keywords
)


def _theme_hit_counts(normalized: str) -> dict[str, int]:
    return {
        theme: sum(1 for keyword in keywords if keyword in normalized)
        for theme, keywords in _SEMANTIC_THEME_KEYWORDS.items()
    }


def _dominant_theme(counts: dict[str, int], *, minimum_hits: int = 3) -> str | None:
    if not counts:
        return None
    theme, hits = max(counts.items(), key=lambda item: item[1])
    return theme if hits >= minimum_hits else None


def _duplicate_paragraph_failures(answer: str) -> tuple[str, ...]:
    seen: set[str] = set()
    seen_themes: set[str] = set()
    for block in _PARAGRAPH_SPLIT_RE.split(str(answer or "").strip()):
        normalized = _normalize(block)
        if not normalized or len(normalized) < 80:
            continue
        if normalized in seen:
            return ("duplicate_paragraph",)
        seen.add(normalized)
        theme = _dominant_theme(_theme_hit_counts(normalized))
        if theme is None:
            continue
        if theme in seen_themes:
            return (f"duplicate_paragraph:{theme}",)
        seen_themes.add(theme)
    return ()


def _drop_semantically_duplicate_paragraphs(answer: str) -> str:
    blocks = _PARAGRAPH_SPLIT_RE.split(str(answer or "").strip())
    if len(blocks) < 2:
        return answer
    kept: list[str] = []
    seen_normalized: set[str] = set()
    theme_to_index: dict[str, int] = {}
    for block in blocks:
        normalized = _normalize(block)
        if not normalized:
            kept.append(block)
            continue
        if len(normalized) < 80:
            kept.append(block)
            continue
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        theme = _dominant_theme(_theme_hit_counts(normalized))
        if theme is None:
            kept.append(block)
            continue
        if theme not in theme_to_index:
            theme_to_index[theme] = len(kept)
            kept.append(block)
            continue
        existing_index = theme_to_index[theme]
        existing_block = kept[existing_index]
        if len(block) > len(existing_block):
            kept[existing_index] = block
    return "\n\n".join(kept)


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
    allowed = {_canonical_money_value(value) for value in fact_sheet.amounts}
    failures = [
        f"unverified_amount:{value}"
        for value in _extract_all(_MONEY_RE, answer)
        if _canonical_money_value(value) not in allowed
    ]
    return tuple(failures)


def _verified_false_missing_fields(sentence: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    has_missing_marker = bool(_FALSE_MISSING_MARKER_RE.search(sentence or ""))
    has_procedure_id_missing_marker = bool(_PROCEDURE_ID_FALSE_MISSING_RE.search(sentence or ""))
    if not has_missing_marker and not has_procedure_id_missing_marker:
        return ()

    available = {
        "procedure_id": bool(fact_sheet.procedure_ids)
        and "procedure_id" not in fact_sheet.conflicts,
        "cig": bool(fact_sheet.cigs) and "cig" not in fact_sheet.conflicts,
        "duration": bool(fact_sheet.durations),
        "amounts": bool(fact_sheet.amounts),
        "locations": bool(fact_sheet.locations),
    }
    return tuple(
        field_key
        for field_key, pattern in _FALSE_MISSING_FIELD_RES
        if available[field_key]
        and (
            (field_key == "procedure_id" and has_procedure_id_missing_marker)
            or (has_missing_marker and pattern.search(sentence))
        )
    )


def _false_missing_fact_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    failures: list[str] = []
    for sentence in _FALSE_MISSING_SENTENCE_RE.findall(answer or ""):
        failures.extend(
            f"false_missing_{field_key}"
            for field_key in _verified_false_missing_fields(sentence, fact_sheet)
        )
    return _unique(failures)


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
    messages = _repair_messages()
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_MONTH_RE,
            allowed_values=fact_sheet.durations,
            suffix=f" {messages.unit_months}",
            failure_prefix="unverified_duration",
        )
    )
    failures.extend(
        _unverified_pattern_failures(
            answer=answer,
            pattern=_YEAR_RE,
            allowed_values=fact_sheet.durations,
            suffix=f" {messages.unit_years}",
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
    failures.extend(_false_missing_fact_failures(answer, fact_sheet))
    failures.extend(_unverified_location_failures(answer, fact_sheet))
    return _unique(failures)


def _replace_unverified_cigs(answer: str, fact_sheet: FactSheet) -> str:
    allowed = {_canonical_token(value) for value in fact_sheet.cigs}
    messages = _repair_messages()

    def replacement(match: re.Match[str]) -> str:
        value = match.group(1)
        if _canonical_token(value) in allowed and "cig" not in fact_sheet.conflicts:
            return match.group(0)
        return messages.unverified_cig

    return _CIG_RE.sub(replacement, answer)


def _replace_unverified_procedure_ids(answer: str, fact_sheet: FactSheet) -> str:
    allowed = {_canonical_token(value) for value in fact_sheet.procedure_ids}
    allowed_exact = {value.strip() for value in fact_sheet.procedure_ids}
    messages = _repair_messages()
    fallback = messages.unverified_procedure_id

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
        return f"{match.group('prefix')}{fallback}"

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
        return f"{match.group('prefix')}{fallback}"

    def replacement(match: re.Match[str]) -> str:
        value = match.group(0)
        if _canonical_token(value) in allowed and "procedure_id" not in fact_sheet.conflicts:
            return value
        return fallback

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


def _unique_fact_sheet_amounts(fact_sheet: FactSheet) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in fact_sheet.amounts:
        canon = _canonical_money_value(value)
        if canon in seen:
            continue
        seen.add(canon)
        unique.append(value)
    return tuple(unique)


def _verified_amount_replacement(fact_sheet: FactSheet) -> str:
    if not fact_sheet.amounts:
        return _repair_messages().unverified_amount
    unique = _unique_fact_sheet_amounts(fact_sheet)
    if len(unique) == 1:
        return unique[0]
    conjunction = _repair_messages().conjunction_and
    return f"{', '.join(unique[:-1])} {conjunction} {unique[-1]}"


def _amount_decimal(value: str) -> Decimal | None:
    canonical = _canonical_money_value(value)
    try:
        return Decimal(canonical)
    except InvalidOperation:
        return None


def _closest_verified_amount(value: str, fact_sheet: FactSheet) -> str | None:
    unique = _unique_fact_sheet_amounts(fact_sheet)
    if not unique:
        return None
    target = _amount_decimal(value)
    if target is None:
        return unique[0]
    best: tuple[Decimal, str] | None = None
    for candidate in unique:
        candidate_amount = _amount_decimal(candidate)
        if candidate_amount is None:
            continue
        distance = abs(candidate_amount - target)
        if best is None or distance < best[0]:
            best = (distance, candidate)
    return best[1] if best is not None else unique[0]


def _replace_unverified_money_values(answer: str, fact_sheet: FactSheet) -> str:
    allowed = {_canonical_money_value(value) for value in fact_sheet.amounts}
    fallback = _repair_messages().unverified_amount

    def replacement(match: re.Match[str]) -> str:
        value = match.group(0)
        if _canonical_money_value(value) in allowed:
            return value
        closest = _closest_verified_amount(value, fact_sheet)
        if closest is not None:
            return closest
        return fallback

    return _MONEY_RE.sub(replacement, answer)


def _false_missing_replacement_fragments(sentence: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    fields = _verified_false_missing_fields(sentence, fact_sheet)
    messages = _repair_messages()
    fragments: list[str] = []
    if "procedure_id" in fields:
        fragments.append(
            f"{messages.fragment_procedure_id_label} "
            f"{', '.join(fact_sheet.procedure_ids)}"
        )
    if "cig" in fields:
        fragments.append(
            f"{messages.fragment_cig_label} {', '.join(fact_sheet.cigs)}"
        )
    if "duration" in fields:
        fragments.append(
            f"{messages.fragment_duration_label} {', '.join(fact_sheet.durations)}"
        )
    if "amounts" in fields:
        fragments.append(
            f"{messages.fragment_amounts_label} "
            f"{_verified_amount_replacement(fact_sheet)}"
        )
    if "locations" in fields:
        fragments.append(
            f"{messages.fragment_locations_label} "
            f"{', '.join(fact_sheet.locations)}"
        )
    return tuple(fragments)


def _replace_false_missing_protected_fact_claims(answer: str, fact_sheet: FactSheet) -> str:
    intro = _repair_messages().verified_data_intro

    def replacement(match: re.Match[str]) -> str:
        sentence = match.group(0)
        fragments = _false_missing_replacement_fragments(sentence, fact_sheet)
        if not fragments:
            return sentence
        leading = sentence[: len(sentence) - len(sentence.lstrip())]
        return f"{leading}{intro}: {'; '.join(fragments)}."

    return _FALSE_MISSING_SENTENCE_RE.sub(replacement, answer)


def _replace_numeric_placeholders(answer: str) -> str:
    messages = _repair_messages()
    repaired = _DAY_PLACEHOLDER_RE.sub(
        lambda match: f"{match.group('prefix')} {messages.unverified_term}",
        answer,
    )
    repaired = _INCOMPLETE_CIG_RE.sub(messages.unverified_cig, repaired)
    return _MASKED_CIG_WITH_VALUE_RE.sub(messages.unverified_cig, repaired)


def _replace_inline_unverified_procedure_id(answer: str, fact_sheet: FactSheet) -> str:
    if (
        len(fact_sheet.procedure_ids) != 1
        or "procedure_id" in fact_sheet.conflicts
    ):
        return answer
    verified = fact_sheet.procedure_ids[0]
    label = _repair_messages().fragment_procedure_id_label
    return _INLINE_UNVERIFIED_PROCEDURE_ID_RE.sub(f"{label} {verified}", answer)


def _replace_inline_unverified_cig(answer: str, fact_sheet: FactSheet) -> str:
    if len(fact_sheet.cigs) != 1 or "cig" in fact_sheet.conflicts:
        return answer
    verified = fact_sheet.cigs[0]
    label = _repair_messages().fragment_cig_label
    return _INLINE_UNVERIFIED_CIG_RE.sub(f"{label} {verified}", answer)


def _strip_contamination_sentences(answer: str) -> str:
    text = str(answer or "")
    if not text.strip():
        return text
    paragraphs = text.split("\n\n")
    cleaned_paragraphs: list[str] = []
    for paragraph in paragraphs:
        sentences = _CONTAMINATION_SENTENCE_SPLIT_RE.split(paragraph)
        kept: list[str] = []
        for sentence in sentences:
            contamination_hits = len(OSCAT_SCT_CONTAMINATION_RE.findall(sentence))
            identity_hits = len(OSCAT_IDENTITY_KEYWORD_RE.findall(sentence))
            if contamination_hits >= 2 and identity_hits == 0:
                continue
            kept.append(sentence)
        cleaned_paragraphs.append(" ".join(kept).strip())
    return "\n\n".join(p for p in cleaned_paragraphs if p)


_MONEY_CLUSTER_GAP_MAX = 12


def _money_cluster_spans(answer: str) -> list[tuple[int, int, str]]:
    matches = list(_MONEY_RE.finditer(answer))
    if not matches:
        return []
    clusters: list[tuple[int, int, list[str]]] = []
    current_start = matches[0].start()
    current_end = matches[0].end()
    current_values = [matches[0].group(0)]
    for match in matches[1:]:
        gap = answer[current_end : match.start()]
        if len(gap) <= _MONEY_CLUSTER_GAP_MAX and re.fullmatch(
            r"[\s,;]+(?:e|ed)?\s*", gap, flags=re.IGNORECASE
        ):
            current_end = match.end()
            current_values.append(match.group(0))
        else:
            clusters.append((current_start, current_end, current_values))
            current_start = match.start()
            current_end = match.end()
            current_values = [match.group(0)]
    clusters.append((current_start, current_end, current_values))
    return [
        (start, end, _normalize(", ".join(values)))
        for start, end, values in clusters
        if len(values) >= 2
    ]


def _dedup_repeated_money_clusters(answer: str) -> str:
    clusters = _money_cluster_spans(answer)
    if len(clusters) < 2:
        return answer
    seen: set[str] = set()
    spans_to_drop: list[tuple[int, int]] = []
    for start, end, key in clusters:
        if key in seen:
            spans_to_drop.append((start, end))
        else:
            seen.add(key)
    if not spans_to_drop:
        return answer
    pieces: list[str] = []
    cursor = 0
    for start, end in spans_to_drop:
        pieces.append(answer[cursor:start])
        cursor = end
    pieces.append(answer[cursor:])
    cleaned = "".join(pieces)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


def _strip_malformed_article_references(answer: str) -> str:
    return _MALFORMED_ARTICLE_RE.sub(_repair_messages().unverified_article, answer)


def _normalize_civil_article_thousand_separator(answer: str) -> str:
    return _CIVIL_ARTICLE_THOUSAND_SEP_RE.sub(r"\1 \2\3", answer)


def _strip_corrupt_money_artifacts(answer: str) -> str:
    return _CORRUPT_MONEY_ARTIFACT_RE.sub(
        _repair_messages().unverified_amount, answer
    )


def _repair_money_range_narrative(answer: str, fact_sheet: FactSheet) -> str:
    if len(fact_sheet.amounts) < 2:
        return answer
    allowed = {_canonical_money_value(value) for value in fact_sheet.amounts}
    template = _repair_messages().distinct_amounts_template

    def replacement(match: re.Match[str]) -> str:
        low_token = match.group(1).strip()
        high_token = match.group(2).strip()
        low_canon = _canonical_money_value(low_token)
        high_canon = _canonical_money_value(high_token)
        if low_canon in allowed and high_canon in allowed and low_canon != high_canon:
            return template.format(low=low_token, high=high_token)
        return match.group(0)

    return _MONEY_RANGE_NARRATIVE_RE.sub(replacement, answer)


def _repair_duration_range_claims(answer: str, fact_sheet: FactSheet) -> str:
    if not fact_sheet.durations:
        return answer
    allowed_numbers = {
        _canonical_number(number)
        for value in fact_sheet.durations
        for number in _NUMBER_RE.findall(value)
    }
    messages = _repair_messages()
    fallback = messages.unverified_duration
    unit_months = messages.unit_months

    def replacement(match: re.Match[str]) -> str:
        low = _canonical_number(match.group(1))
        high = _canonical_number(match.group(2))
        low_ok = low in allowed_numbers
        high_ok = high in allowed_numbers
        if low_ok and high_ok and low != high:
            return match.group(0)
        if high_ok and not low_ok:
            return f"{match.group(2)} {unit_months}"
        if low_ok and not high_ok:
            return f"{match.group(1)} {unit_months}"
        return fallback

    return _DURATION_RANGE_RE.sub(replacement, answer)


def repair_unsupported_protected_facts(answer: str, fact_sheet: FactSheet) -> str:
    """Mask unsupported protected facts while preserving the rest of the answer."""

    repaired = str(answer or "")
    repaired = _strip_contamination_sentences(repaired)
    repaired = _drop_semantically_duplicate_paragraphs(repaired)
    repaired = _strip_corrupt_money_artifacts(repaired)
    repaired = _normalize_civil_article_thousand_separator(repaired)
    repaired = _strip_malformed_article_references(repaired)
    repaired = _replace_inline_unverified_procedure_id(repaired, fact_sheet)
    repaired = _repair_duration_range_claims(repaired, fact_sheet)
    repaired = _repair_money_range_narrative(repaired, fact_sheet)
    repaired = _replace_numeric_placeholders(repaired)
    repaired = _replace_inline_unverified_cig(repaired, fact_sheet)
    repaired = _replace_false_missing_protected_fact_claims(repaired, fact_sheet)
    repaired = _replace_unverified_cigs(repaired, fact_sheet)
    repaired = _replace_unverified_procedure_ids(repaired, fact_sheet)
    messages = _repair_messages()
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_DAY_RE,
        allowed_values=fact_sheet.critical_days,
        replacement_text=messages.unverified_days,
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_MONTH_RE,
        allowed_values=fact_sheet.durations,
        replacement_text=messages.unverified_duration,
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_YEAR_RE,
        allowed_values=fact_sheet.durations,
        replacement_text=messages.unverified_duration,
    )
    repaired = _replace_unverified_pattern_values(
        repaired,
        pattern=_PERCENT_RE,
        allowed_values=fact_sheet.percentages,
        replacement_text=messages.unverified_percentage,
    )
    repaired = _dedup_repeated_money_clusters(repaired)
    repaired = _replace_unverified_money_values(repaired, fact_sheet)
    repaired = _replace_unverified_token_values(
        repaired,
        pattern=_ADDRESS_RE,
        allowed_values=fact_sheet.locations,
        replacement_text=messages.unverified_location,
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

    em = _engine_messages()
    empty_markers = {"", em.fact_sheet_value_not_detected, em.fact_sheet_value_no_conflicts}

    def split_values(key: str, prefix: str = "") -> tuple[str, ...]:
        raw = values.get(key, "")
        if raw in empty_markers:
            return ()
        parts = tuple(part.strip() for part in raw.split(", ") if part.strip())
        if prefix:
            return tuple(part.removeprefix(prefix).strip() for part in parts)
        return parts

    status_value = values.get(em.fact_sheet_label_status, FactStatus.NOT_DETECTED.value)
    try:
        status = FactStatus(status_value)
    except ValueError:
        status = FactStatus.NOT_DETECTED
    return FactSheet(
        procedure_label=values.get(em.fact_sheet_label_procedure, em.procedure_label_unattributed),
        procedure_ids=split_values(em.fact_sheet_label_procedure_id),
        cigs=split_values(em.fact_sheet_label_cig, "CIG "),
        critical_days=split_values(em.fact_sheet_label_critical_days),
        durations=split_values(em.fact_sheet_label_duration),
        amounts=split_values(em.fact_sheet_label_amounts),
        locations=split_values(em.fact_sheet_label_locations),
        percentages=split_values(em.fact_sheet_label_percentages),
        source_ids=split_values(em.fact_sheet_label_sources),
        conflicts=split_values(em.fact_sheet_label_conflicts),
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


_CRITICAL_FAILURE_PREFIXES: tuple[str, ...] = (
    "fact_sheet_conflict",
    "cross_procedure_mixing",
    "wrong_procedure_label",
    "duplicate_paragraph",
    "masked_cig_value",
    "numeric_placeholder",
)


def filter_long_form_amounts(
    fact_sheet: FactSheet,
    *,
    minimum_eur: Decimal = Decimal("5000"),
) -> FactSheet:
    """Drop fact-sheet amounts below the long-form materiality threshold.

    Long-form tender overviews should only quote material monetary values
    (importo a base di gara, valore globale stimato). Smaller administrative
    figures (cauzioni minime, tariffe, marche da bollo) pollute the
    replacement cluster and surface noise in the rendered narrative.
    Falls back to the original list when no amount clears the threshold.
    """

    from dataclasses import replace as dc_replace

    if not fact_sheet.amounts:
        return fact_sheet
    kept: list[str] = []
    for value in fact_sheet.amounts:
        amount = _amount_decimal(value)
        if amount is None:
            continue
        if amount >= minimum_eur:
            kept.append(value)
    if not kept or len(kept) == len(fact_sheet.amounts):
        return fact_sheet if kept or not fact_sheet.amounts else fact_sheet
    return dc_replace(fact_sheet, amounts=tuple(kept))


def fact_sheet_missing_critical_slots(
    fact_sheet: FactSheet,
    *,
    minimum_amount_eur: Decimal = Decimal("100000"),
) -> tuple[str, ...]:
    """Return critical OSCAT/SCT slots missing from the fact sheet.

    Used for observability: long-form tender overviews should at minimum
    surface a procedure id, a duration, and a non-trivial amount. When any
    of these is absent the guardrails will likely block a faithful answer,
    so callers can downgrade the guardrail mode or boost retrieval.
    """

    if fact_sheet.procedure_label not in PROCEDURE_ANCHORS:
        return ()
    missing: list[str] = []
    if not fact_sheet.procedure_ids:
        missing.append("procedure_id")
    if not fact_sheet.durations:
        missing.append("duration")
    has_major_amount = False
    for value in fact_sheet.amounts:
        canonical = _canonical_money_value(value)
        try:
            if Decimal(canonical) >= minimum_amount_eur:
                has_major_amount = True
                break
        except InvalidOperation:
            continue
    if not has_major_amount:
        missing.append("major_amount")
    return tuple(missing)


def classify_guardrail_failures(
    failures: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split failures into (critical, soft) buckets.

    Critical failures justify a hard block of the entire answer. Soft failures
    can be repaired in-place (numeric masking, replacement) without nuking the
    surrounding narrative.
    """

    critical: list[str] = []
    soft: list[str] = []
    for failure in failures:
        if any(failure.startswith(prefix) for prefix in _CRITICAL_FAILURE_PREFIXES):
            critical.append(failure)
        else:
            soft.append(failure)
    return tuple(critical), tuple(soft)


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
