"""Operational backfill helpers for the requirement graph foundation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RequirementExtractionRun, TenderRequirement
from app.services.requirement_candidates import list_staged_requirement_candidate_runs
from app.services.requirement_consolidation import (
    rebuild_consolidated_requirements_from_legacy,
    rebuild_consolidated_requirements_from_staging,
)


@dataclass(frozen=True)
class RequirementGraphBackfillTenderResult:
    tender_id: int
    status: str
    source: str = "none"
    consolidated_count: int = 0


@dataclass(frozen=True)
class RequirementGraphBackfillSummary:
    results: tuple[RequirementGraphBackfillTenderResult, ...]
    dry_run: bool
    limit_runs: int

    @property
    def tender_count(self) -> int:
        return len(self.results)

    @property
    def rebuilt_count(self) -> int:
        return sum(1 for result in self.results if result.status == "rebuilt")

    @property
    def planned_count(self) -> int:
        return sum(1 for result in self.results if result.status == "planned")


def _normalize_tender_ids(tender_ids: Iterable[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_id in tender_ids:
        tender_id = int(raw_id)
        if tender_id <= 0:
            raise ValueError("tender ids must be positive integers")
        if tender_id in seen:
            continue
        seen.add(tender_id)
        normalized.append(tender_id)
    return normalized


async def list_requirement_graph_backfill_tender_ids(
    db: AsyncSession,
    *,
    tender_ids: Iterable[int] | None = None,
) -> list[int]:
    """Return tender ids that should be rebuilt from staged requirement runs."""

    if tender_ids is not None:
        return _normalize_tender_ids(tender_ids)

    result = await db.execute(
        select(RequirementExtractionRun.tender_id)
        .distinct()
        .order_by(RequirementExtractionRun.tender_id.asc())
    )
    staged_ids = list(result.scalars().all())
    legacy_result = await db.execute(
        select(TenderRequirement.tender_id).distinct().order_by(TenderRequirement.tender_id.asc())
    )
    legacy_ids = list(legacy_result.scalars().all())
    return _normalize_tender_ids([*staged_ids, *legacy_ids])


async def backfill_requirement_graphs(
    db: AsyncSession,
    *,
    tender_ids: Iterable[int] | None = None,
    limit_runs: int = 5,
    dry_run: bool = False,
) -> RequirementGraphBackfillSummary:
    """Rebuild requirement graphs for tenders with staged extraction data."""

    if limit_runs < 1:
        raise ValueError("limit_runs must be at least 1")

    resolved_tender_ids = await list_requirement_graph_backfill_tender_ids(
        db,
        tender_ids=tender_ids,
    )
    results: list[RequirementGraphBackfillTenderResult] = []

    for tender_id in resolved_tender_ids:
        if dry_run:
            results.append(
                RequirementGraphBackfillTenderResult(
                    tender_id=tender_id,
                    status="planned",
                )
            )
            continue

        extraction_runs = await list_staged_requirement_candidate_runs(
            db,
            tender_id=tender_id,
            limit_runs=limit_runs,
        )
        source = "staging" if extraction_runs else "legacy"
        if extraction_runs:
            consolidated_rows = await rebuild_consolidated_requirements_from_staging(
                db,
                tender_id=tender_id,
                limit_runs=limit_runs,
            )
        else:
            consolidated_rows = await rebuild_consolidated_requirements_from_legacy(
                db,
                tender_id=tender_id,
            )
        status = "rebuilt" if consolidated_rows else "skipped"
        results.append(
            RequirementGraphBackfillTenderResult(
                tender_id=tender_id,
                status=status,
                source=source,
                consolidated_count=len(consolidated_rows),
            )
        )

    return RequirementGraphBackfillSummary(
        results=tuple(results),
        dry_run=dry_run,
        limit_runs=limit_runs,
    )
