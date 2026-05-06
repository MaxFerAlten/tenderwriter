"""Helpers to consolidate staged requirement candidates into canonical requirements."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ConsolidatedRequirement,
    RequirementCandidate,
    RequirementExtractionRun,
    RequirementRelation,
    TenderRequirement,
)
from app.services.requirement_candidates import list_staged_requirement_candidate_runs
from app.services.tender_requirements import normalize_requirement_text

_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
_DOCUMENT_ROLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("clarification", ("clarif", "chiariment", "quesit", "q&a", "faq", "rispost", "answer")),
    ("disciplinare", ("disciplin",)),
    ("capitolato", ("capitol", "specification", "statement-of-work", "sow")),
    ("bando", ("bando", "notice", "invitation", "tender-notice")),
    ("annex", ("annex", "allegat", "appendix", "attachment", "modul", "template", "form")),
)
_DOCUMENT_ROLE_RANK = {
    "clarification": 60,
    "disciplinare": 50,
    "capitolato": 40,
    "bando": 30,
    "annex": 20,
    "other": 10,
}
_PRECEDENCE_POLICY_VERSION = "document_role_v1"
_ACTIVE_GRAPH_STATE = "active"
_OBSOLETE_GRAPH_STATE = "obsolete"
_PRESERVED_METADATA_KEYS = ("review_count", "latest_review")
_WHITESPACE_RE = re.compile(r"\s+")
_RELATION_TOKEN_RE = re.compile(r"[a-z0-9]+")
_RELATION_STOPWORDS = {
    "a",
    "an",
    "and",
    "con",
    "da",
    "dei",
    "degli",
    "del",
    "della",
    "delle",
    "dello",
    "di",
    "e",
    "for",
    "gli",
    "i",
    "if",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "of",
    "or",
    "per",
    "provided",
    "subject",
    "that",
    "the",
    "to",
    "un",
    "una",
    "with",
}
_RELATION_OVERLAP_THRESHOLD = 0.8
_DEPENDENCY_MARKERS: tuple[str, ...] = (
    "after",
    "following",
    "only after",
    "subject to",
    "conditioned on",
    "provided that",
    "once",
    "upon",
    "previa",
    "dopo",
    "a seguito di",
    "subordinato a",
)
_DEPENDENCY_OVERLAP_THRESHOLD = 0.6
_GRAPH_V2_METADATA_KEYS = ("applicability", "conditions", "exceptions", "parent_requirement_key")
_CONFLICT_NUMBER_RE = re.compile(
    r"\b\d+(?:[,.]\d+)?(?:\s?(?:%|months?|mesi|days?|giorni|hours?|ore|years?|anni))?\b"
)
_NEGATION_MARKERS: tuple[str, ...] = (
    "not required",
    "not mandatory",
    "shall not",
    "must not",
    "non richiesto",
    "non obbligatorio",
    "non deve",
    "non dovra",
    "facoltativo",
    "optional",
)
_MANDATORY_MARKERS: tuple[str, ...] = (
    "required",
    "mandatory",
    "must",
    "shall",
    "deve",
    "dovra",
    "obbligatorio",
    "richiesto",
)
_OVERRIDE_MARKERS: tuple[str, ...] = (
    "replaces",
    "supersedes",
    "overrides",
    "amends",
    "updates",
    "instead of",
    "sostituisce",
    "rettifica",
    "modifica",
    "aggiorna",
    "prevale",
)


def _normalize_priority(value: Any) -> str:
    priority = str(value or "medium").strip().casefold()
    if priority not in _PRIORITY_RANK:
        return "medium"
    return priority


def _normalize_graph_state(value: Any, *, default: str = _ACTIVE_GRAPH_STATE) -> str | None:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        normalized = default
    if normalized == "all":
        return None
    if normalized not in {_ACTIVE_GRAPH_STATE, _OBSOLETE_GRAPH_STATE}:
        return default
    return normalized


def _normalize_document_role(value: Any) -> str | None:
    normalized = _WHITESPACE_RE.sub(" ", str(value or "").strip()).casefold()
    if not normalized:
        return None

    for role, patterns in _DOCUMENT_ROLE_PATTERNS:
        if normalized == role:
            return role
        if any(pattern in normalized for pattern in patterns):
            return role
    if normalized in _DOCUMENT_ROLE_RANK:
        return normalized
    return None


def _extract_document_role_hint(*payloads: Mapping[str, Any] | None) -> str | None:
    for payload in payloads:
        if not payload:
            continue
        for key in (
            "document_role",
            "document_kind",
            "source_document_kind",
            "document_type",
            "doc_type",
            "role",
        ):
            role = _normalize_document_role(payload.get(key))
            if role:
                return role
    return None


def _raw_candidate_payload(candidate: RequirementCandidate) -> Mapping[str, Any]:
    if isinstance(candidate.metadata_json, Mapping):
        raw_candidate = candidate.metadata_json.get("raw_candidate") or {}
        if isinstance(raw_candidate, Mapping):
            return raw_candidate
    return {}


def _candidate_is_rejected_by_verifier(candidate: RequirementCandidate) -> bool:
    raw_candidate = _raw_candidate_payload(candidate)
    verification = raw_candidate.get("verification") if isinstance(raw_candidate, Mapping) else None
    verification_state = raw_candidate.get("verification_state")
    if isinstance(verification, Mapping):
        verification_state = verification.get("state") or verification_state
    return str(verification_state or "").strip().casefold() == "rejected"


def _clean_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    cleaned: list[str] = []
    for item in values:
        normalized = _WHITESPACE_RE.sub(" ", str(item or "").strip())
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _clean_applicability(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        cleaned_values = _clean_text_list(value)
        return {"values": cleaned_values} if cleaned_values else {}
    cleaned = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    return {"text": cleaned} if cleaned else {}


def _clean_parent_requirement_key(value: Any) -> str | None:
    cleaned = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    return cleaned or None


def _extract_graph_v2_payload_from_candidate(candidate: RequirementCandidate) -> dict[str, Any]:
    raw_candidate = _raw_candidate_payload(candidate)
    graph_payload = {
        "applicability": _clean_applicability(raw_candidate.get("applicability")),
        "conditions": _clean_text_list(raw_candidate.get("conditions")),
        "exceptions": _clean_text_list(raw_candidate.get("exceptions")),
        "parent_requirement_key": _clean_parent_requirement_key(
            raw_candidate.get("parent_requirement_key")
        ),
    }
    return graph_payload


def _merge_text_lists(left: Any, right: Any) -> list[str]:
    merged = _clean_text_list(left)
    for item in _clean_text_list(right):
        if item not in merged:
            merged.append(item)
    return merged


def _merge_applicability(left: Any, right: Any) -> dict[str, Any]:
    merged = _clean_applicability(left)
    for key, value in _clean_applicability(right).items():
        if key not in merged or not merged[key]:
            merged[key] = value
        elif merged[key] != value:
            existing_values = merged[key] if isinstance(merged[key], list) else [merged[key]]
            incoming_values = value if isinstance(value, list) else [value]
            merged[key] = [
                *existing_values,
                *[item for item in incoming_values if item not in existing_values],
            ]
    return merged


def _merge_graph_v2_payload(existing: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    existing["conditions"] = _merge_text_lists(
        existing.get("conditions"), incoming.get("conditions")
    )
    existing["exceptions"] = _merge_text_lists(
        existing.get("exceptions"), incoming.get("exceptions")
    )
    existing["applicability"] = _merge_applicability(
        existing.get("applicability"), incoming.get("applicability")
    )
    if not existing.get("parent_requirement_key") and incoming.get("parent_requirement_key"):
        existing["parent_requirement_key"] = _clean_parent_requirement_key(
            incoming.get("parent_requirement_key")
        )

    metadata_json = dict(existing.get("metadata_json") or {})
    graph_v2 = dict(metadata_json.get("graph_v2") or {})
    for key in _GRAPH_V2_METADATA_KEYS:
        if existing.get(key) not in (None, "", [], {}):
            graph_v2[key] = existing[key]
    metadata_json["graph_v2"] = graph_v2
    existing["metadata_json"] = metadata_json


def _infer_document_role(
    extraction_run: RequirementExtractionRun,
    candidate: RequirementCandidate,
) -> str:
    raw_candidate = _raw_candidate_payload(candidate)

    hinted_role = _extract_document_role_hint(
        raw_candidate,
        candidate.metadata_json if isinstance(candidate.metadata_json, Mapping) else None,
        extraction_run.metadata_json if isinstance(extraction_run.metadata_json, Mapping) else None,
    )
    if hinted_role:
        return hinted_role

    searchable_parts = [
        str(candidate.source_document_ref or ""),
        str(extraction_run.source_document_ref or ""),
        str(extraction_run.filename or ""),
    ]
    searchable_text = " ".join(part for part in searchable_parts if part).casefold()
    for role, patterns in _DOCUMENT_ROLE_PATTERNS:
        if any(pattern in searchable_text for pattern in patterns):
            return role
    return "other"


def _source_sort_key(source_payload: Mapping[str, Any]) -> tuple[int, float, int, int]:
    return (
        int(source_payload.get("precedence_rank") or 0),
        float(
            source_payload.get("confidence")
            if source_payload.get("confidence") is not None
            else -1.0
        ),
        int(source_payload.get("extraction_run_id") or 0),
        int(source_payload.get("candidate_id") or 0),
    )


def _is_better_source(
    candidate_source: Mapping[str, Any], current_source: Mapping[str, Any] | None
) -> bool:
    if current_source is None:
        return True
    return _source_sort_key(candidate_source) > _source_sort_key(current_source)


def _build_source_payload(
    extraction_run: RequirementExtractionRun,
    candidate: RequirementCandidate,
) -> dict[str, Any]:
    document_role = _infer_document_role(extraction_run, candidate)
    raw_candidate = _raw_candidate_payload(candidate)
    payload = {
        "candidate_id": candidate.id,
        "extraction_run_id": extraction_run.id,
        "source_document_ref": candidate.source_document_ref or extraction_run.source_document_ref,
        "source_reference": candidate.source_reference,
        "filename": extraction_run.filename,
        "priority": _normalize_priority(candidate.priority),
        "confidence": candidate.confidence,
        "document_role": document_role,
        "precedence_rank": _DOCUMENT_ROLE_RANK.get(document_role, _DOCUMENT_ROLE_RANK["other"]),
        "summary_text": str(candidate.summary_text or "").strip(),
    }
    verification = raw_candidate.get("verification")
    if isinstance(verification, Mapping):
        payload["verification"] = dict(verification)
    return payload


def _merge_graph_metadata(
    existing_metadata: Mapping[str, Any] | None,
    fresh_metadata: Mapping[str, Any] | None,
    *,
    graph_state: str,
    reason: str | None = None,
) -> dict[str, Any]:
    merged = {
        **dict(existing_metadata or {}),
        **dict(fresh_metadata or {}),
    }
    for key in _PRESERVED_METADATA_KEYS:
        if existing_metadata and key in existing_metadata:
            merged[key] = existing_metadata[key]

    lifecycle = dict((existing_metadata or {}).get("lifecycle") or {})
    lifecycle["graph_state"] = graph_state
    if reason:
        lifecycle["reason"] = reason
    else:
        lifecycle.pop("reason", None)
    merged["lifecycle"] = lifecycle
    return merged


def _refresh_metadata(existing: dict[str, Any]) -> None:
    metadata_json = dict(existing.get("metadata_json") or {})
    sources = list(metadata_json.get("sources") or [])
    sources.sort(key=_source_sort_key, reverse=True)

    document_roles: list[str] = []
    document_refs: list[str] = []
    for source in sources:
        role = str(source.get("document_role") or "other")
        if role not in document_roles:
            document_roles.append(role)
        ref = source.get("source_document_ref")
        if ref and ref not in document_refs:
            document_refs.append(str(ref))

    primary_source = sources[0] if sources else None
    if primary_source is not None:
        for index, source in enumerate(sources):
            source["is_primary"] = index == 0

    variant_summaries: list[str] = []
    for source in sources:
        summary_text = _WHITESPACE_RE.sub(" ", str(source.get("summary_text") or "").strip())
        if summary_text and summary_text not in variant_summaries:
            variant_summaries.append(summary_text)

    metadata_json["sources"] = sources
    metadata_json["primary_source"] = primary_source
    metadata_json["source_document_roles"] = document_roles
    metadata_json["source_document_refs"] = document_refs
    metadata_json["cross_document"] = len(document_refs) > 1
    metadata_json["merge_kind"] = (
        "cross_document_duplicate" if len(document_refs) > 1 else "single_document"
    )
    metadata_json["precedence_policy"] = _PRECEDENCE_POLICY_VERSION
    metadata_json["document_precedence"] = {
        "policy": _PRECEDENCE_POLICY_VERSION,
        "primary_role": primary_source.get("document_role")
        if isinstance(primary_source, Mapping)
        else None,
        "primary_precedence_rank": (
            primary_source.get("precedence_rank") if isinstance(primary_source, Mapping) else None
        ),
        "primary_source_document_ref": (
            primary_source.get("source_document_ref")
            if isinstance(primary_source, Mapping)
            else None
        ),
        "ordered_roles": document_roles,
        "superseded_sources": [
            {
                "document_role": source.get("document_role") or "other",
                "precedence_rank": source.get("precedence_rank"),
                "source_document_ref": source.get("source_document_ref"),
                "source_reference": source.get("source_reference"),
                "summary_text": source.get("summary_text"),
            }
            for source in sources[1:]
        ],
        "resolution": (
            "source_precedence"
            if len(sources) > 1 and len({source.get("precedence_rank") for source in sources}) > 1
            else "same_precedence_or_single_source"
        ),
    }
    metadata_json["source_variants"] = {
        "variant_count": len(variant_summaries),
        "has_variants": len(variant_summaries) > 1,
        "examples": variant_summaries[:5],
    }
    existing["metadata_json"] = metadata_json


def _extract_primary_source(requirement: ConsolidatedRequirement) -> Mapping[str, Any]:
    metadata_json = (
        requirement.metadata_json if isinstance(requirement.metadata_json, Mapping) else {}
    )
    primary_source = metadata_json.get("primary_source") or {}
    return primary_source if isinstance(primary_source, Mapping) else {}


def _extract_primary_document_role(requirement: ConsolidatedRequirement) -> str:
    primary_source = _extract_primary_source(requirement)
    role = _normalize_document_role(primary_source.get("document_role"))
    if role:
        return role
    return "other"


def _requirement_relation_text(requirement: ConsolidatedRequirement) -> str:
    return normalize_requirement_text(
        requirement.normalized_text or requirement.canonical_text or ""
    )


def _extract_primary_document_ref(requirement: ConsolidatedRequirement) -> str | None:
    primary_source = _extract_primary_source(requirement)
    ref = primary_source.get("source_document_ref")
    return str(ref).strip() if ref else None


def _requirements_are_cross_document(
    left_requirement: ConsolidatedRequirement,
    right_requirement: ConsolidatedRequirement,
) -> bool:
    left_ref = _extract_primary_document_ref(left_requirement)
    right_ref = _extract_primary_document_ref(right_requirement)
    if left_ref and right_ref:
        return left_ref != right_ref
    return _extract_primary_document_role(left_requirement) != _extract_primary_document_role(
        right_requirement
    )


def _contains_marker(value: str, markers: Sequence[str]) -> bool:
    return any(marker in value for marker in markers)


def _extract_override_markers(*requirements: ConsolidatedRequirement) -> list[str]:
    text = " ".join(_requirement_relation_text(requirement) for requirement in requirements)
    return [marker for marker in _OVERRIDE_MARKERS if marker in text]


def _extract_conflict_signals(
    left_requirement: ConsolidatedRequirement,
    right_requirement: ConsolidatedRequirement,
) -> list[str]:
    left_text = _requirement_relation_text(left_requirement)
    right_text = _requirement_relation_text(right_requirement)
    signals: list[str] = []

    left_numbers = set(_CONFLICT_NUMBER_RE.findall(left_text))
    right_numbers = set(_CONFLICT_NUMBER_RE.findall(right_text))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        signals.append("numeric_mismatch")

    left_negated = _contains_marker(left_text, _NEGATION_MARKERS)
    right_negated = _contains_marker(right_text, _NEGATION_MARKERS)
    left_mandatory = _contains_marker(left_text, _MANDATORY_MARKERS)
    right_mandatory = _contains_marker(right_text, _MANDATORY_MARKERS)
    if left_negated != right_negated and (
        left_mandatory or right_mandatory or left_negated or right_negated
    ):
        signals.append("polarity_mismatch")

    return signals


def _relation_document_metadata(
    source_requirement: ConsolidatedRequirement,
    target_requirement: ConsolidatedRequirement,
    *,
    source_role: str,
    target_role: str,
    source_rank: int,
    target_rank: int,
) -> dict[str, Any]:
    return {
        "precedence_policy": _PRECEDENCE_POLICY_VERSION,
        "source_role": source_role,
        "target_role": target_role,
        "source_precedence_rank": source_rank,
        "target_precedence_rank": target_rank,
        "source_document_ref": _extract_primary_document_ref(source_requirement),
        "target_document_ref": _extract_primary_document_ref(target_requirement),
    }


def _requirement_parent_lookup_keys(requirement: ConsolidatedRequirement) -> set[str]:
    keys = {
        normalize_requirement_text(requirement.normalized_text or requirement.canonical_text or ""),
        normalize_requirement_text(requirement.canonical_text or ""),
        str(requirement.id or "").strip().casefold(),
    }
    metadata_json = (
        requirement.metadata_json if isinstance(requirement.metadata_json, Mapping) else {}
    )
    graph_v2 = (
        metadata_json.get("graph_v2") if isinstance(metadata_json.get("graph_v2"), Mapping) else {}
    )
    for key in ("requirement_key", "parent_requirement_key"):
        value = graph_v2.get(key)
        if value:
            keys.add(normalize_requirement_text(str(value)))
    return {key for key in keys if key}


def _resolve_parent_requirement_links(requirements: Sequence[ConsolidatedRequirement]) -> None:
    lookup: dict[str, ConsolidatedRequirement] = {}
    for requirement in requirements:
        for key in _requirement_parent_lookup_keys(requirement):
            lookup.setdefault(key, requirement)

    for requirement in requirements:
        parent_key = _clean_parent_requirement_key(
            getattr(requirement, "parent_requirement_key", None)
        )
        if not parent_key:
            requirement.parent_requirement_id = None
            continue
        parent = lookup.get(normalize_requirement_text(parent_key))
        if parent is None or parent is requirement or not getattr(parent, "id", None):
            requirement.parent_requirement_id = None
            continue
        requirement.parent_requirement_id = parent.id


def _tokenize_relation_text(value: str | None) -> set[str]:
    normalized = normalize_requirement_text(value or "")
    return {
        token
        for token in _RELATION_TOKEN_RE.findall(normalized)
        if len(token) > 1 and token not in _RELATION_STOPWORDS
    }


def _relation_overlap(
    left_requirement: ConsolidatedRequirement,
    right_requirement: ConsolidatedRequirement,
) -> tuple[float, list[str]]:
    left_tokens = _tokenize_relation_text(
        left_requirement.normalized_text or left_requirement.canonical_text
    )
    right_tokens = _tokenize_relation_text(
        right_requirement.normalized_text or right_requirement.canonical_text
    )
    if not left_tokens or not right_tokens:
        return 0.0, []

    shared_tokens = sorted(left_tokens & right_tokens)
    if len(shared_tokens) < 3:
        return 0.0, shared_tokens

    overlap = len(shared_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap, shared_tokens


def _extract_dependency_clauses(requirement: ConsolidatedRequirement) -> list[str]:
    normalized_text = normalize_requirement_text(
        requirement.normalized_text or requirement.canonical_text or ""
    )
    clauses: list[str] = []
    if not normalized_text:
        return clauses

    for marker in _DEPENDENCY_MARKERS:
        pattern = re.escape(marker)
        for match in re.finditer(pattern, normalized_text):
            clause = normalized_text[match.end() :].strip(" ,.;:-")
            if clause:
                clauses.append(clause)
    return clauses


def _dependency_clause_overlap(
    clause: str, requirement: ConsolidatedRequirement
) -> tuple[float, list[str]]:
    clause_tokens = _tokenize_relation_text(clause)
    target_tokens = _tokenize_relation_text(
        requirement.normalized_text or requirement.canonical_text
    )
    if not clause_tokens or not target_tokens:
        return 0.0, []

    shared_tokens = sorted(clause_tokens & target_tokens)
    if len(shared_tokens) < 2:
        return 0.0, shared_tokens

    overlap = len(shared_tokens) / min(len(clause_tokens), len(target_tokens))
    return overlap, shared_tokens


def build_requirement_relation_payloads(
    requirements: Sequence[ConsolidatedRequirement],
) -> list[dict[str, Any]]:
    """Infer requirement relations between persisted consolidated requirements."""

    relation_items: list[dict[str, Any]] = []
    ordered_requirements = list(requirements)

    for child_requirement in ordered_requirements:
        parent_requirement_id = int(getattr(child_requirement, "parent_requirement_id", None) or 0)
        child_requirement_id = int(getattr(child_requirement, "id", None) or 0)
        if (
            not parent_requirement_id
            or not child_requirement_id
            or parent_requirement_id == child_requirement_id
        ):
            continue
        relation_items.append(
            {
                "source_requirement_id": parent_requirement_id,
                "target_requirement_id": child_requirement_id,
                "relation_type": "parent_of",
                "confidence": 1.0,
                "metadata_json": {
                    "inference_method": "explicit_parent_requirement_key_v1",
                    "parent_requirement_key": getattr(
                        child_requirement, "parent_requirement_key", None
                    ),
                },
            }
        )

    for index, left_requirement in enumerate(ordered_requirements):
        left_id = getattr(left_requirement, "id", None)
        left_text = _requirement_relation_text(left_requirement)
        if not left_id or not left_text:
            continue

        left_role = _extract_primary_document_role(left_requirement)
        left_rank = _DOCUMENT_ROLE_RANK.get(left_role, _DOCUMENT_ROLE_RANK["other"])

        for right_requirement in ordered_requirements[index + 1 :]:
            right_id = getattr(right_requirement, "id", None)
            right_text = _requirement_relation_text(right_requirement)
            if not right_id or not right_text or left_text == right_text:
                continue

            right_role = _extract_primary_document_role(right_requirement)
            right_rank = _DOCUMENT_ROLE_RANK.get(right_role, _DOCUMENT_ROLE_RANK["other"])

            overlap, shared_tokens = _relation_overlap(left_requirement, right_requirement)
            if overlap < _RELATION_OVERLAP_THRESHOLD:
                continue

            conflict_signals = _extract_conflict_signals(left_requirement, right_requirement)
            if left_rank == right_rank:
                if conflict_signals and _requirements_are_cross_document(
                    left_requirement, right_requirement
                ):
                    relation_items.append(
                        {
                            "source_requirement_id": left_requirement.id,
                            "target_requirement_id": right_requirement.id,
                            "relation_type": "conflicts_with",
                            "confidence": round(overlap, 4),
                            "metadata_json": {
                                "inference_method": "cross_document_conflict_v1",
                                "shared_terms": shared_tokens,
                                "conflict_signals": conflict_signals,
                                **_relation_document_metadata(
                                    left_requirement,
                                    right_requirement,
                                    source_role=left_role,
                                    target_role=right_role,
                                    source_rank=left_rank,
                                    target_rank=right_rank,
                                ),
                            },
                        }
                    )
                continue

            if left_rank > right_rank:
                source_requirement = left_requirement
                source_role = left_role
                source_rank = left_rank
                target_requirement = right_requirement
                target_role = right_role
                target_rank = right_rank
            else:
                source_requirement = right_requirement
                source_role = right_role
                source_rank = right_rank
                target_requirement = left_requirement
                target_role = left_role
                target_rank = left_rank

            override_markers = _extract_override_markers(source_requirement, target_requirement)
            relation_items.append(
                {
                    "source_requirement_id": source_requirement.id,
                    "target_requirement_id": target_requirement.id,
                    "relation_type": "overrides",
                    "confidence": round(overlap, 4),
                    "metadata_json": {
                        "inference_method": (
                            "explicit_precedence_override_v1"
                            if override_markers
                            else "lexical_override_v1"
                        ),
                        "shared_terms": shared_tokens,
                        "conflict_signals": conflict_signals,
                        "override_markers": override_markers,
                        **_relation_document_metadata(
                            source_requirement,
                            target_requirement,
                            source_role=source_role,
                            target_role=target_role,
                            source_rank=source_rank,
                            target_rank=target_rank,
                        ),
                    },
                }
            )

    for source_requirement in ordered_requirements:
        source_id = getattr(source_requirement, "id", None)
        source_text = normalize_requirement_text(
            source_requirement.normalized_text or source_requirement.canonical_text or ""
        )
        if not source_id or not source_text:
            continue

        dependency_clauses = _extract_dependency_clauses(source_requirement)
        if not dependency_clauses:
            continue

        best_target_payloads: dict[int, dict[str, Any]] = {}
        for target_requirement in ordered_requirements:
            target_id = getattr(target_requirement, "id", None)
            target_text = normalize_requirement_text(
                target_requirement.normalized_text or target_requirement.canonical_text or ""
            )
            if not target_id or target_id == source_id or not target_text:
                continue

            best_overlap = 0.0
            best_shared_tokens: list[str] = []
            best_clause = ""
            for clause in dependency_clauses:
                overlap, shared_tokens = _dependency_clause_overlap(clause, target_requirement)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_shared_tokens = shared_tokens
                    best_clause = clause

            if best_overlap < _DEPENDENCY_OVERLAP_THRESHOLD:
                continue

            target_payload = {
                "source_requirement_id": source_id,
                "target_requirement_id": target_id,
                "relation_type": "depends_on",
                "confidence": round(best_overlap, 4),
                "metadata_json": {
                    "inference_method": "dependency_clause_v1",
                    "matched_clause": best_clause,
                    "shared_terms": best_shared_tokens,
                },
            }
            best_target_payloads[target_id] = target_payload

        relation_items.extend(best_target_payloads.values())

    relation_items.sort(
        key=lambda item: (
            item["source_requirement_id"],
            item["target_requirement_id"],
            item["relation_type"],
        )
    )
    return relation_items


def build_consolidated_requirement_payloads(
    extraction_runs: Sequence[RequirementExtractionRun],
) -> list[dict[str, Any]]:
    """Merge staged candidates into canonical requirement payloads."""

    consolidated_by_text: dict[str, dict[str, Any]] = {}

    for extraction_run in extraction_runs:
        ordered_candidates = sorted(
            list(extraction_run.candidates or []),
            key=lambda candidate: (candidate.candidate_position or 0, candidate.id or 0),
        )
        for candidate in ordered_candidates:
            if _candidate_is_rejected_by_verifier(candidate):
                continue
            normalized_text = normalize_requirement_text(
                candidate.normalized_text or candidate.summary_text or ""
            )
            canonical_text = str(candidate.summary_text or "").strip()
            if not normalized_text or not canonical_text:
                continue

            source_payload = _build_source_payload(extraction_run, candidate)
            graph_v2_payload = _extract_graph_v2_payload_from_candidate(candidate)

            existing = consolidated_by_text.get(normalized_text)
            if existing is None:
                consolidated_by_text[normalized_text] = {
                    "canonical_text": canonical_text,
                    "normalized_text": normalized_text,
                    "category": candidate.category,
                    "priority": _normalize_priority(candidate.priority),
                    "confidence": candidate.confidence,
                    "source_count": 1,
                    "consolidation_method": "staging_v1",
                    "review_state": "pending",
                    "applicability": graph_v2_payload["applicability"],
                    "conditions": graph_v2_payload["conditions"],
                    "exceptions": graph_v2_payload["exceptions"],
                    "parent_requirement_key": graph_v2_payload["parent_requirement_key"],
                    "metadata_json": {
                        "sources": [source_payload],
                        "extraction_run_ids": [extraction_run.id],
                    },
                }
                _merge_graph_v2_payload(consolidated_by_text[normalized_text], graph_v2_payload)
                _refresh_metadata(consolidated_by_text[normalized_text])
                continue

            existing["source_count"] += 1
            _merge_graph_v2_payload(existing, graph_v2_payload)
            if candidate.confidence is not None and (
                existing["confidence"] is None or candidate.confidence > existing["confidence"]
            ):
                existing["confidence"] = candidate.confidence
            if (
                _PRIORITY_RANK[_normalize_priority(candidate.priority)]
                > _PRIORITY_RANK[existing["priority"]]
            ):
                existing["priority"] = _normalize_priority(candidate.priority)

            metadata_json = dict(existing.get("metadata_json") or {})
            sources = list(metadata_json.get("sources") or [])
            sources.append(source_payload)
            run_ids = list(metadata_json.get("extraction_run_ids") or [])
            if extraction_run.id not in run_ids:
                run_ids.append(extraction_run.id)
            metadata_json["sources"] = sources
            metadata_json["extraction_run_ids"] = run_ids
            existing["metadata_json"] = metadata_json
            _refresh_metadata(existing)

            primary_source = dict(existing.get("metadata_json") or {}).get("primary_source")
            if (
                isinstance(primary_source, Mapping)
                and primary_source.get("candidate_id") == source_payload.get("candidate_id")
                and primary_source.get("extraction_run_id")
                == source_payload.get("extraction_run_id")
            ):
                existing["canonical_text"] = canonical_text
                if candidate.category:
                    existing["category"] = candidate.category
            elif not existing.get("category") and candidate.category:
                existing["category"] = candidate.category

    consolidated_items = list(consolidated_by_text.values())
    consolidated_items.sort(
        key=lambda item: (-_PRIORITY_RANK[item["priority"]], item["canonical_text"].casefold()),
    )
    return consolidated_items


def _build_legacy_source_payload(requirement: TenderRequirement) -> dict[str, Any]:
    return {
        "legacy_requirement_id": requirement.id,
        "source_document_ref": None,
        "source_reference": requirement.category,
        "filename": None,
        "priority": _normalize_priority(requirement.priority),
        "confidence": None,
        "document_role": "other",
        "precedence_rank": _DOCUMENT_ROLE_RANK["other"],
        "summary_text": str(requirement.requirement_text or "").strip(),
        "compliance_status": getattr(
            requirement.compliance_status, "value", requirement.compliance_status
        ),
    }


def build_consolidated_requirement_payloads_from_legacy(
    requirements: Sequence[TenderRequirement],
) -> list[dict[str, Any]]:
    """Convert legacy tender_requirements rows into graph-ready payloads."""

    consolidated_by_text: dict[str, dict[str, Any]] = {}
    for requirement in sorted(list(requirements or []), key=lambda item: item.id or 0):
        normalized_text = normalize_requirement_text(requirement.requirement_text or "")
        canonical_text = str(requirement.requirement_text or "").strip()
        if not normalized_text or not canonical_text:
            continue

        source_payload = _build_legacy_source_payload(requirement)
        existing = consolidated_by_text.get(normalized_text)
        if existing is None:
            consolidated_by_text[normalized_text] = {
                "canonical_text": canonical_text,
                "normalized_text": normalized_text,
                "category": requirement.category,
                "priority": _normalize_priority(requirement.priority),
                "confidence": None,
                "source_count": 1,
                "consolidation_method": "legacy_tender_requirements_v1",
                "review_state": "pending",
                "metadata_json": {
                    "sources": [source_payload],
                    "legacy_requirement_ids": [requirement.id],
                },
            }
            _refresh_metadata(consolidated_by_text[normalized_text])
            continue

        existing["source_count"] += 1
        if (
            _PRIORITY_RANK[_normalize_priority(requirement.priority)]
            > _PRIORITY_RANK[existing["priority"]]
        ):
            existing["priority"] = _normalize_priority(requirement.priority)
        metadata_json = dict(existing.get("metadata_json") or {})
        sources = list(metadata_json.get("sources") or [])
        sources.append(source_payload)
        legacy_requirement_ids = list(metadata_json.get("legacy_requirement_ids") or [])
        if requirement.id not in legacy_requirement_ids:
            legacy_requirement_ids.append(requirement.id)
        metadata_json["sources"] = sources
        metadata_json["legacy_requirement_ids"] = legacy_requirement_ids
        existing["metadata_json"] = metadata_json
        _refresh_metadata(existing)

    consolidated_items = list(consolidated_by_text.values())
    consolidated_items.sort(
        key=lambda item: (-_PRIORITY_RANK[item["priority"]], item["canonical_text"].casefold()),
    )
    return consolidated_items


async def _load_existing_consolidated_requirements(
    db: AsyncSession,
    *,
    tender_id: int,
) -> list[ConsolidatedRequirement]:
    result = await db.execute(
        select(ConsolidatedRequirement).where(ConsolidatedRequirement.tender_id == tender_id)
    )
    return list(result.scalars().all())


async def _load_existing_requirement_relations(
    db: AsyncSession,
    *,
    tender_id: int,
) -> list[RequirementRelation]:
    result = await db.execute(
        select(RequirementRelation).where(RequirementRelation.tender_id == tender_id)
    )
    return list(result.scalars().all())


async def replace_consolidated_requirements(
    db: AsyncSession,
    *,
    tender_id: int,
    consolidated_items: Sequence[dict[str, Any]],
    consolidation_method: str = "staging_v1",
) -> list[ConsolidatedRequirement]:
    """Synchronize the consolidated requirements stored for a tender."""

    existing_rows = await _load_existing_consolidated_requirements(db, tender_id=tender_id)
    existing_by_text = {
        normalize_requirement_text(row.normalized_text or row.canonical_text or ""): row
        for row in existing_rows
    }
    active_texts: set[str] = set()
    rows: list[ConsolidatedRequirement] = []
    for item in consolidated_items:
        normalized_text = str(item["normalized_text"]).strip()
        active_texts.add(normalized_text)
        existing_row = existing_by_text.get(normalized_text)
        fresh_metadata = dict(item.get("metadata_json") or {})
        review_state = str(item.get("review_state") or "pending")

        if existing_row is not None:
            existing_row.canonical_text = str(item["canonical_text"]).strip()
            existing_row.normalized_text = normalized_text
            existing_row.category = item.get("category")
            existing_row.priority = _normalize_priority(item.get("priority"))
            existing_row.confidence = item.get("confidence")
            existing_row.source_count = int(item.get("source_count") or 0)
            existing_row.consolidation_method = str(
                item.get("consolidation_method") or consolidation_method
            )
            existing_row.review_state = str(existing_row.review_state or review_state)
            existing_row.graph_state = _ACTIVE_GRAPH_STATE
            existing_row.parent_requirement_key = _clean_parent_requirement_key(
                item.get("parent_requirement_key")
            )
            existing_row.applicability = _clean_applicability(item.get("applicability"))
            existing_row.conditions = _clean_text_list(item.get("conditions"))
            existing_row.exceptions = _clean_text_list(item.get("exceptions"))
            existing_row.metadata_json = _merge_graph_metadata(
                existing_row.metadata_json
                if isinstance(existing_row.metadata_json, Mapping)
                else None,
                fresh_metadata,
                graph_state=_ACTIVE_GRAPH_STATE,
            )
            rows.append(existing_row)
            continue

        row = ConsolidatedRequirement(
            tender_id=tender_id,
            canonical_text=str(item["canonical_text"]).strip(),
            normalized_text=normalized_text,
            category=item.get("category"),
            priority=_normalize_priority(item.get("priority")),
            confidence=item.get("confidence"),
            source_count=int(item.get("source_count") or 0),
            consolidation_method=str(item.get("consolidation_method") or consolidation_method),
            review_state=review_state,
            graph_state=_ACTIVE_GRAPH_STATE,
            parent_requirement_key=_clean_parent_requirement_key(
                item.get("parent_requirement_key")
            ),
            applicability=_clean_applicability(item.get("applicability")),
            conditions=_clean_text_list(item.get("conditions")),
            exceptions=_clean_text_list(item.get("exceptions")),
            metadata_json=_merge_graph_metadata(
                None,
                fresh_metadata,
                graph_state=_ACTIVE_GRAPH_STATE,
            ),
        )
        db.add(row)
        rows.append(row)

    for existing_row in existing_rows:
        existing_text = normalize_requirement_text(
            existing_row.normalized_text or existing_row.canonical_text or ""
        )
        if existing_text in active_texts:
            continue
        existing_row.graph_state = _OBSOLETE_GRAPH_STATE
        existing_row.metadata_json = _merge_graph_metadata(
            existing_row.metadata_json if isinstance(existing_row.metadata_json, Mapping) else None,
            None,
            graph_state=_OBSOLETE_GRAPH_STATE,
            reason="missing_from_latest_rebuild",
        )

    await db.flush()
    _resolve_parent_requirement_links(rows)
    await db.flush()
    return rows


async def replace_requirement_relations(
    db: AsyncSession,
    *,
    tender_id: int,
    relation_items: Sequence[dict[str, Any]],
) -> list[RequirementRelation]:
    """Synchronize persisted requirement relations for a tender."""

    existing_rows = await _load_existing_requirement_relations(db, tender_id=tender_id)
    existing_by_key = {
        (
            int(row.source_requirement_id or 0),
            int(row.target_requirement_id or 0),
            str(row.relation_type or "").strip().casefold(),
        ): row
        for row in existing_rows
    }
    active_keys: set[tuple[int, int, str]] = set()
    rows: list[RequirementRelation] = []
    for item in relation_items:
        source_requirement_id = int(item["source_requirement_id"])
        target_requirement_id = int(item["target_requirement_id"])
        relation_type = str(item["relation_type"]).strip().casefold()
        key = (
            source_requirement_id,
            target_requirement_id,
            relation_type,
        )
        active_keys.add(key)
        existing_row = existing_by_key.get(key)
        fresh_metadata = dict(item.get("metadata_json") or {})
        review_state = str(item.get("review_state") or "pending")

        if existing_row is not None:
            existing_row.confidence = item.get("confidence")
            existing_row.review_state = str(existing_row.review_state or review_state)
            existing_row.graph_state = _ACTIVE_GRAPH_STATE
            existing_row.metadata_json = _merge_graph_metadata(
                existing_row.metadata_json
                if isinstance(existing_row.metadata_json, Mapping)
                else None,
                fresh_metadata,
                graph_state=_ACTIVE_GRAPH_STATE,
            )
            rows.append(existing_row)
            continue

        row = RequirementRelation(
            tender_id=tender_id,
            source_requirement_id=source_requirement_id,
            target_requirement_id=target_requirement_id,
            relation_type=relation_type,
            confidence=item.get("confidence"),
            review_state=review_state,
            graph_state=_ACTIVE_GRAPH_STATE,
            metadata_json=_merge_graph_metadata(
                None,
                fresh_metadata,
                graph_state=_ACTIVE_GRAPH_STATE,
            ),
        )
        db.add(row)
        rows.append(row)

    for existing_row in existing_rows:
        existing_key = (
            int(existing_row.source_requirement_id or 0),
            int(existing_row.target_requirement_id or 0),
            str(existing_row.relation_type or "").strip().casefold(),
        )
        if existing_key in active_keys:
            continue
        existing_row.graph_state = _OBSOLETE_GRAPH_STATE
        existing_row.metadata_json = _merge_graph_metadata(
            existing_row.metadata_json if isinstance(existing_row.metadata_json, Mapping) else None,
            None,
            graph_state=_OBSOLETE_GRAPH_STATE,
            reason="missing_from_latest_rebuild",
        )

    await db.flush()
    return rows


async def rebuild_consolidated_requirements_from_staging(
    db: AsyncSession,
    *,
    tender_id: int,
    limit_runs: int = 5,
) -> list[ConsolidatedRequirement]:
    """Rebuild consolidated requirements for a tender from staged candidates."""

    extraction_runs = await list_staged_requirement_candidate_runs(
        db,
        tender_id=tender_id,
        limit_runs=limit_runs,
    )
    consolidated_items = build_consolidated_requirement_payloads(extraction_runs)
    consolidated_rows = await replace_consolidated_requirements(
        db,
        tender_id=tender_id,
        consolidated_items=consolidated_items,
    )
    relation_items = build_requirement_relation_payloads(consolidated_rows)
    await replace_requirement_relations(
        db,
        tender_id=tender_id,
        relation_items=relation_items,
    )
    return consolidated_rows


async def rebuild_consolidated_requirements_from_legacy(
    db: AsyncSession,
    *,
    tender_id: int,
) -> list[ConsolidatedRequirement]:
    """Rebuild consolidated requirements for a tender from legacy materialized rows."""

    result = await db.execute(
        select(TenderRequirement)
        .where(TenderRequirement.tender_id == tender_id)
        .order_by(TenderRequirement.id.asc())
    )
    legacy_requirements = list(result.scalars().all())
    consolidated_items = build_consolidated_requirement_payloads_from_legacy(legacy_requirements)
    consolidated_rows = await replace_consolidated_requirements(
        db,
        tender_id=tender_id,
        consolidated_items=consolidated_items,
    )
    relation_items = build_requirement_relation_payloads(consolidated_rows)
    await replace_requirement_relations(
        db,
        tender_id=tender_id,
        relation_items=relation_items,
    )
    return consolidated_rows


async def list_consolidated_requirements(
    db: AsyncSession,
    *,
    tender_id: int,
    graph_state: str | None = _ACTIVE_GRAPH_STATE,
) -> list[ConsolidatedRequirement]:
    """Return persisted consolidated requirements for a tender."""

    normalized_state = _normalize_graph_state(graph_state)
    statement = select(ConsolidatedRequirement).where(
        ConsolidatedRequirement.tender_id == tender_id,
    )
    if normalized_state is not None:
        statement = statement.where(ConsolidatedRequirement.graph_state == normalized_state)

    result = await db.execute(
        statement.order_by(
            ConsolidatedRequirement.created_at.desc(),
            ConsolidatedRequirement.id.desc(),
        )
    )
    return list(result.scalars().all())


async def list_requirement_relations(
    db: AsyncSession,
    *,
    tender_id: int,
    relation_type: str | None = None,
    graph_state: str | None = _ACTIVE_GRAPH_STATE,
) -> list[RequirementRelation]:
    """Return persisted requirement relations for a tender."""

    normalized_state = _normalize_graph_state(graph_state)
    statement = (
        select(RequirementRelation)
        .where(RequirementRelation.tender_id == tender_id)
        .options(
            selectinload(RequirementRelation.source_requirement),
            selectinload(RequirementRelation.target_requirement),
        )
        .order_by(
            RequirementRelation.created_at.desc(),
            RequirementRelation.id.desc(),
        )
    )
    if normalized_state is not None:
        statement = statement.where(RequirementRelation.graph_state == normalized_state)
    if relation_type:
        statement = statement.where(
            RequirementRelation.relation_type == str(relation_type).strip().casefold()
        )

    result = await db.execute(statement)
    return list(result.scalars().all())
