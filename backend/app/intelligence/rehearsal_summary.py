"""Produce the ``rehearsal_summary`` block consumed by the forecast view.

The KPI forecast endpoint is owned by the external
``kpi-reason-engine`` service — we cannot mutate its formulas.  PR-10
therefore attaches a *local* enrichment block derived from the most
recent completed :class:`RehearsalRun` of a tender (optionally scoped
to a single proposal):

.. code-block:: json

    {
      "rehearsal_summary": {
        "last_rehearsal_at": "2026-04-17T18:40:00Z",
        "overall_score": 71.4,
        "persona_divergence": 0.28,
        "blocking_findings": 3,
        "high_severity_rework_suggestions": 2,
        "health_projection": "amber",
        "run_id": 42,
        "proposal_id": 7,
        "version": "tw-rehearsal-v1"
      }
    }

No-rehearsal case returns ``None`` (the API layer turns that into the
empty block or a 404 depending on context).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    RehearsalPersonaResult,
    RehearsalRecommendation,
    RehearsalRun,
    RehearsalRunStatus,
)

logger = logging.getLogger(__name__)


_SUMMARY_VERSION = "tw-rehearsal-v1"


async def _latest_completed_run(
    db: AsyncSession, *, tender_id: int, proposal_id: int | None
) -> RehearsalRun | None:
    stmt = (
        select(RehearsalRun)
        .where(RehearsalRun.tender_id == tender_id)
        .where(RehearsalRun.status == RehearsalRunStatus.COMPLETED)
        .order_by(RehearsalRun.completed_at.desc(), RehearsalRun.id.desc())
        .limit(1)
    )
    if proposal_id is not None:
        stmt = stmt.where(RehearsalRun.proposal_id == proposal_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _blocking_findings_count(db: AsyncSession, *, run_id: int) -> int:
    stmt = select(func.coalesce(func.sum(RehearsalPersonaResult.blocking_findings_count), 0)).where(
        RehearsalPersonaResult.rehearsal_run_id == run_id
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def _high_severity_rework_count(db: AsyncSession, *, run_id: int) -> int:
    stmt = select(func.count()).where(
        and_(
            RehearsalRecommendation.rehearsal_run_id == run_id,
            RehearsalRecommendation.severity == "high",
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def build_rehearsal_summary(
    db: AsyncSession,
    *,
    tender_id: int,
    proposal_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the forecast enrichment block or ``None`` if no completed run."""

    run = await _latest_completed_run(db, tender_id=tender_id, proposal_id=proposal_id)
    if run is None:
        return None

    blocking = await _blocking_findings_count(db, run_id=run.id)
    high_sev_rework = await _high_severity_rework_count(db, run_id=run.id)

    return {
        "run_id": run.id,
        "tender_id": run.tender_id,
        "proposal_id": run.proposal_id,
        "last_rehearsal_at": (run.completed_at.isoformat() if run.completed_at else None),
        "overall_score": (
            round(float(run.overall_score), 2) if run.overall_score is not None else None
        ),
        "persona_divergence": (
            round(float(run.persona_divergence), 3) if run.persona_divergence is not None else None
        ),
        "blocking_findings": blocking,
        "high_severity_rework_suggestions": high_sev_rework,
        "health_projection": run.health_projection,
        "version": _SUMMARY_VERSION,
    }


def empty_rehearsal_summary() -> dict[str, Any]:
    """Return the shape used when no rehearsal has completed yet."""

    return {
        "run_id": None,
        "last_rehearsal_at": None,
        "overall_score": None,
        "persona_divergence": None,
        "blocking_findings": 0,
        "high_severity_rework_suggestions": 0,
        "health_projection": None,
        "version": _SUMMARY_VERSION,
    }


__all__ = [
    "build_rehearsal_summary",
    "empty_rehearsal_summary",
]
