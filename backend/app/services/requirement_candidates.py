"""Staging helpers for raw requirement candidates extracted from tender documents."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RequirementCandidate, RequirementExtractionRun
from app.services.tender_requirements import normalize_requirement_text


def _clean_summary_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_priority(value: Any) -> str:
    priority = str(value or "medium").strip().casefold()
    if priority not in {"high", "medium", "low"}:
        return "medium"
    return priority


def _normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def stage_extracted_requirement_candidates(
    db: AsyncSession,
    *,
    tender_id: int,
    actor_id: int | None,
    source_document_ref: str | None,
    filename: str | None,
    extraction_method: str,
    candidates: Sequence[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> tuple[RequirementExtractionRun, list[RequirementCandidate]]:
    """Persist a staging snapshot of extracted candidates with provenance."""

    raw_candidates = list(candidates)
    run = RequirementExtractionRun(
        tender_id=tender_id,
        actor_id=actor_id,
        source_document_ref=source_document_ref,
        filename=filename,
        extraction_method=str(extraction_method or "heuristic_v1"),
        candidate_count=0,
        metadata_json=dict(metadata or {}),
    )
    db.add(run)
    await db.flush()

    staged_candidates: list[RequirementCandidate] = []
    seen_normalized: set[str] = set()

    for position, candidate in enumerate(raw_candidates, start=1):
        summary = _clean_summary_text(candidate.get("summary") or "")
        if len(summary) < 15:
            continue

        normalized = normalize_requirement_text(summary)
        if not normalized or normalized in seen_normalized:
            continue

        seen_normalized.add(normalized)
        reference = (
            candidate.get("reference")
            or candidate.get("section")
            or candidate.get("source_section")
        )
        category = candidate.get("category") or reference
        staged_candidate = RequirementCandidate(
            tender_id=tender_id,
            extraction_run_id=run.id,
            candidate_position=position,
            source_document_ref=source_document_ref,
            source_reference=str(reference) if reference is not None else None,
            summary_text=summary,
            normalized_text=normalized,
            category=str(category) if category is not None else None,
            priority=_normalize_priority(candidate.get("priority")),
            confidence=_normalize_confidence(candidate.get("confidence")),
            metadata_json={"raw_candidate": dict(candidate)},
        )
        db.add(staged_candidate)
        staged_candidates.append(staged_candidate)

    run.candidate_count = len(staged_candidates)
    run.metadata_json = {
        **dict(run.metadata_json or {}),
        "raw_candidate_count": len(raw_candidates),
        "staged_candidate_count": len(staged_candidates),
    }

    await db.flush()
    return run, staged_candidates


async def list_staged_requirement_candidate_runs(
    db: AsyncSession,
    *,
    tender_id: int,
    limit_runs: int = 5,
) -> list[RequirementExtractionRun]:
    """Return recent staged extraction runs with candidates for a tender."""

    normalized_limit = max(1, min(int(limit_runs), 20))
    result = await db.execute(
        select(RequirementExtractionRun)
        .where(RequirementExtractionRun.tender_id == tender_id)
        .options(selectinload(RequirementExtractionRun.candidates))
        .order_by(RequirementExtractionRun.created_at.desc(), RequirementExtractionRun.id.desc())
        .limit(normalized_limit)
    )
    runs = list(result.scalars().all())
    for run in runs:
        run.candidates = sorted(
            list(run.candidates or []),
            key=lambda candidate: (candidate.candidate_position or 0, candidate.id or 0),
        )
    return runs
