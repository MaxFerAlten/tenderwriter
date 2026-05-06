"""LLM v2 requirement extraction with schema validation and source citations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.intelligence.ontology import attach_ontology_to_candidates
from app.services.requirement_verification import verify_requirement_candidates
from app.services.tender_requirements import normalize_requirement_text

EXTRACTION_METHOD = "llm_v2"
SCHEMA_VERSION = "requirement_extraction_v2.schema.v1"
_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_DEFAULT_CONTEXT_WINDOW = 4096
_PROMPT_RESERVE_TOKENS = 512
_APPROX_CHARS_PER_TOKEN = 3
_MIN_PROMPT_TEXT_CHARS = 1200
_PROMPT_WINDOW_OVERLAP_CHARS = 300
_PRIORITY_MAP = {
    "critical": "high",
    "mandatory": "high",
    "must": "high",
    "must-have": "high",
    "required": "high",
    "shall": "high",
    "high": "high",
    "should": "medium",
    "should-have": "medium",
    "medium": "medium",
    "recommended": "medium",
    "nice-to-have": "low",
    "optional": "low",
    "low": "low",
}


class RequirementExtractionV2Citation(BaseModel):
    model_config = ConfigDict(extra="allow")

    quote: str = Field(min_length=1)
    source_document_ref: str | None = None
    source_reference: str | None = None
    section_path: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None

    @field_validator("quote", mode="before")
    @classmethod
    def clean_quote(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())


class RequirementExtractionV2Item(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_text: str = Field(min_length=15)
    category: str | None = "general"
    priority: str | None = "medium"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    applicability: str | dict[str, Any] | list[Any] | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    parent_requirement_key: str | None = None
    citations: list[RequirementExtractionV2Citation] = Field(min_length=1)

    @field_validator("requirement_text", mode="before")
    @classmethod
    def clean_requirement_text(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

    @field_validator("category", "priority", "parent_requirement_key", mode="before")
    @classmethod
    def clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"\s+", " ", str(value).strip())
        return cleaned or None

    @field_validator("conditions", "exceptions", mode="before")
    @classmethod
    def clean_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        cleaned = [re.sub(r"\s+", " ", str(item).strip()) for item in values]
        return [item for item in cleaned if item]


def requirement_extraction_v2_json_schema() -> dict[str, Any]:
    """Return the strict response schema expected from the LLM prompt."""

    return {
        "schema_version": SCHEMA_VERSION,
        "requirements": [RequirementExtractionV2Item.model_json_schema()],
    }


def _strip_json_fences(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = _JSON_FENCE_RE.sub("", text).strip()
    return text


def _extract_json_payload(value: str) -> Any:
    text = _strip_json_fences(value)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not starts:
            raise
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


def _coerce_requirement_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    coerced = dict(payload)
    if "requirement_text" not in coerced and "text" in coerced:
        coerced["requirement_text"] = coerced["text"]
    if "category" not in coerced and "type" in coerced:
        coerced["category"] = coerced["type"]

    citations = []
    for citation in list(coerced.get("citations") or coerced.get("source_citations") or []):
        citation_payload = dict(citation)
        if "quote" not in citation_payload:
            for alias in ("excerpt", "source_quote", "text"):
                if citation_payload.get(alias):
                    citation_payload["quote"] = citation_payload[alias]
                    break
        citations.append(citation_payload)
    coerced["citations"] = citations
    return coerced


def _normalize_priority(value: str | None) -> str:
    raw = str(value or "medium").strip().casefold()
    return _PRIORITY_MAP.get(raw, "medium")


def _source_reference_from_citation(citation: RequirementExtractionV2Citation) -> str | None:
    if citation.source_reference:
        return citation.source_reference
    parts = []
    if citation.section_path:
        parts.append(citation.section_path)
    if citation.page is not None:
        parts.append(f"p. {citation.page}")
    return " · ".join(parts) if parts else None


def parse_requirement_extraction_v2_response(
    response_text: str,
    *,
    source_document_ref: str | None = None,
    section_path: str | None = None,
) -> list[dict[str, Any]]:
    """Parse and normalize an LLM v2 JSON response into staging candidates."""

    payload = _extract_json_payload(response_text)
    raw_requirements = payload.get("requirements") if isinstance(payload, Mapping) else payload
    if not isinstance(raw_requirements, list):
        raise ValueError("LLM v2 response must contain a requirements array")

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_requirement in raw_requirements:
        if not isinstance(raw_requirement, Mapping):
            continue
        try:
            requirement = RequirementExtractionV2Item.model_validate(
                _coerce_requirement_payload(raw_requirement)
            )
        except ValidationError:
            continue

        normalized = normalize_requirement_text(requirement.requirement_text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        citation_payloads = []
        for citation in requirement.citations:
            citation_payload = citation.model_dump(exclude_none=True)
            if source_document_ref and not citation_payload.get("source_document_ref"):
                citation_payload["source_document_ref"] = source_document_ref
            if section_path and not citation_payload.get("section_path"):
                citation_payload["section_path"] = section_path
            citation_payloads.append(citation_payload)

        primary_citation = RequirementExtractionV2Citation.model_validate(citation_payloads[0])
        source_reference = _source_reference_from_citation(primary_citation) or section_path
        candidates.append(
            {
                "summary": requirement.requirement_text,
                "reference": source_reference,
                "section": source_reference,
                "source_section": source_reference,
                "priority": _normalize_priority(requirement.priority),
                "category": requirement.category or "general",
                "confidence": requirement.confidence,
                "citations": citation_payloads,
                "conditions": requirement.conditions,
                "exceptions": requirement.exceptions,
                "applicability": requirement.applicability,
                "parent_requirement_key": requirement.parent_requirement_key,
                "schema_version": SCHEMA_VERSION,
                "extraction_method": EXTRACTION_METHOD,
            }
        )
    return attach_ontology_to_candidates(candidates)


def _iter_section_inputs(
    *,
    document_text: str,
    section_texts: Mapping[str, str] | None,
    max_sections: int,
    max_input_chars: int,
) -> Iterable[tuple[str, str]]:
    sections = [
        (str(section_path or "Document").strip(), str(text or "").strip())
        for section_path, text in dict(section_texts or {}).items()
        if str(text or "").strip()
    ]
    if not sections:
        sections = [("Document", str(document_text or "").strip())]

    emitted = 0
    limit = max(1, max_sections)
    for section_path, text in sections:
        for window_text in _split_text_for_prompt(text, max_chars=max_input_chars):
            if emitted >= limit:
                return
            yield section_path, window_text
            emitted += 1


def _estimate_max_input_chars(
    *,
    context_window: int,
    max_tokens: int,
) -> int:
    available_prompt_tokens = max(
        256,
        int(context_window) - int(max_tokens) - _PROMPT_RESERVE_TOKENS,
    )
    return max(
        _MIN_PROMPT_TEXT_CHARS,
        available_prompt_tokens * _APPROX_CHARS_PER_TOKEN,
    )


def _split_text_for_prompt(
    text: str,
    *,
    max_chars: int,
) -> list[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    windows: list[str] = []
    start = 0
    text_length = len(cleaned)
    while start < text_length:
        end = min(text_length, start + max_chars)
        if end < text_length:
            boundary = max(
                cleaned.rfind("\n\n", start, end),
                cleaned.rfind(". ", start, end),
                cleaned.rfind("; ", start, end),
                cleaned.rfind(": ", start, end),
                cleaned.rfind(" ", start, end),
            )
            if boundary > start + (max_chars // 2):
                end = boundary + 1
        window = cleaned[start:end].strip()
        if window:
            windows.append(window)
        if end >= text_length:
            break
        start = max(end - _PROMPT_WINDOW_OVERLAP_CHARS, start + 1)
    return windows


def build_requirement_extraction_v2_prompt_variables(
    *,
    document_text: str,
    source_document_ref: str | None,
    section_path: str,
    extra_variables: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    variables = {
        "schema_version": SCHEMA_VERSION,
        "source_document_ref": source_document_ref or "",
        "section_path": section_path,
        "document_text": document_text,
    }
    if extra_variables:
        variables.update(dict(extra_variables))
    return variables


async def extract_requirement_candidates_v2_from_sections(
    generator: Any,
    *,
    document_text: str,
    section_texts: Mapping[str, str] | None = None,
    source_document_ref: str | None = None,
    max_sections: int = 12,
    max_tokens: int = 2048,
    context_window: int = _DEFAULT_CONTEXT_WINDOW,
    template_name: str = "requirement_extractor_v2",
    prompt_variables: Mapping[str, Any] | None = None,
    candidate_annotations: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run LLM v2 extraction section-by-section and return staged candidate payloads."""

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_input_chars = _estimate_max_input_chars(
        context_window=context_window,
        max_tokens=max_tokens,
    )
    for section_path, section_text in _iter_section_inputs(
        document_text=document_text,
        section_texts=section_texts,
        max_sections=max_sections,
        max_input_chars=max_input_chars,
    ):
        if len(section_text) < 40:
            continue
        result = await generator.generate(
            template_name,
            build_requirement_extraction_v2_prompt_variables(
                document_text=section_text,
                source_document_ref=source_document_ref,
                section_path=section_path,
                extra_variables=prompt_variables,
            ),
            temperature=0.05,
            max_tokens=max_tokens,
        )
        response_text = str(getattr(result, "text", result) or "")
        parsed_candidates = parse_requirement_extraction_v2_response(
            response_text,
            source_document_ref=source_document_ref,
            section_path=section_path,
        )
        verified_candidates = verify_requirement_candidates(
            parsed_candidates,
            source_text=section_text,
        )
        for candidate in verified_candidates:
            normalized = normalize_requirement_text(candidate.get("summary"))
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if candidate_annotations:
                candidate = {
                    **dict(candidate_annotations),
                    **candidate,
                }
            candidates.append(candidate)
    return candidates
