"""Provider-agnostic tender document requirement extraction orchestration."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.config import settings as app_settings
from app.services.requirement_extraction_v2 import (
    extract_requirement_candidates_v2_from_sections,
)
from app.services.requirement_rollout import should_use_requirement_extraction_llm_v2

_LLM_STATUS_RE = re.compile(r"status\s+(?P<status>\d{3})", re.IGNORECASE)
PARTICIPATION_REQUIREMENT_SCOPE = "participation"
PARTICIPATION_EXTRACTOR_PIPELINE = "tender_document_llm_participation_v1"


@dataclass(slots=True)
class TenderRequirementExtractionResult:
    candidates: list[dict[str, Any]]
    extraction_method: str
    warnings: list[dict[str, object]] = field(default_factory=list)
    requirement_scope: str = "general"
    extractor_pipeline: str = "heuristic_fallback_v1"


def compact_extraction_error_message(value: object, *, limit: int = 500) -> str:
    message = re.sub(r"\s+", " ", str(value or "").strip())
    if len(message) <= limit:
        return message
    return f"{message[: limit - 3].rstrip()}..."


def build_llm_extraction_warning(
    exc: Exception,
    *,
    fallback_method: str,
) -> dict[str, object]:
    message = compact_extraction_error_message(exc)
    warning: dict[str, object] = {
        "code": "llm_extraction_failed",
        "title": "LLM requirement extraction warning",
        "message": message,
        "source": "requirement_extraction_llm_v2",
        "severity": "warning",
        "fallback_applied": True,
        "fallback_method": fallback_method,
        "fallback_message": (
            f"The import continued with the {fallback_method} fallback extractor."
        ),
    }
    match = _LLM_STATUS_RE.search(message)
    if match:
        warning["status_code"] = int(match.group("status"))
    return warning


def _annotate_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    requirement_scope: str,
    extractor_pipeline: str,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = dict(candidate)
        payload.setdefault("requirement_scope", requirement_scope)
        payload.setdefault("extractor_pipeline", extractor_pipeline)
        annotated.append(payload)
    return annotated


async def extract_tender_participation_requirements(
    *,
    generator: Any | None,
    document_text: str,
    section_texts: Mapping[str, str] | None,
    source_document_ref: str | None,
    tender_id: int | None,
    fallback_candidates: Sequence[Mapping[str, Any]] | None = None,
    settings: Any = app_settings,
) -> TenderRequirementExtractionResult:
    """Extract participation requirements from a tender document using an LLM first.

    The caller provides fallback heuristic candidates so the orchestration can keep
    the current system behavior when the LLM path is disabled or fails, while the
    public contract stays focused on the document-level extraction goal.
    """

    fallback_payload = _annotate_candidates(
        fallback_candidates or [],
        requirement_scope="general",
        extractor_pipeline="heuristic_fallback_v1",
    )
    if generator is None:
        return TenderRequirementExtractionResult(
            candidates=fallback_payload,
            extraction_method="heuristic_v1",
        )

    if not should_use_requirement_extraction_llm_v2(settings, tender_id=tender_id):
        return TenderRequirementExtractionResult(
            candidates=fallback_payload,
            extraction_method="heuristic_v1",
        )

    try:
        llm_candidates = await extract_requirement_candidates_v2_from_sections(
            generator,
            document_text=document_text,
            section_texts=section_texts,
            source_document_ref=source_document_ref,
            max_sections=getattr(settings, "requirement_extraction_llm_v2_max_sections", 12),
            max_tokens=getattr(settings, "requirement_extraction_llm_v2_max_tokens", 2048),
            template_name="participation_requirement_extractor_v1",
            candidate_annotations={
                "requirement_scope": PARTICIPATION_REQUIREMENT_SCOPE,
                "extractor_pipeline": PARTICIPATION_EXTRACTOR_PIPELINE,
            },
        )
        if llm_candidates:
            return TenderRequirementExtractionResult(
                candidates=llm_candidates,
                extraction_method="llm_v2",
                requirement_scope=PARTICIPATION_REQUIREMENT_SCOPE,
                extractor_pipeline=PARTICIPATION_EXTRACTOR_PIPELINE,
            )
    except Exception as exc:
        return TenderRequirementExtractionResult(
            candidates=fallback_payload,
            extraction_method="heuristic_v1",
            warnings=[
                build_llm_extraction_warning(
                    exc,
                    fallback_method="heuristic_v1",
                )
            ],
        )

    return TenderRequirementExtractionResult(
        candidates=fallback_payload,
        extraction_method="heuristic_v1",
    )
