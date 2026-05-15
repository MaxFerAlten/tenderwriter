"""Convert rehearsal recommendations into operational rework actions.

A :class:`RehearsalRecommendation` is an *advisory* artefact produced
by the rehearsal orchestrator.  It is never created side-effect-free
from the workflow tables — it is merely *surfaced* to operators.  When
an operator explicitly accepts one (PR-09), this module materialises
a real :class:`ReworkAction` bound to the appropriate
:class:`ContributionUnit`, then flips the recommendation into the
``ACCEPTED`` state and records the linkage.

Dismissal is the inverse: the operator ignores the recommendation and
writes the decision back so it is not re-created on the next rehearsal.

Only ``PROPOSED`` recommendations are mutable.  Attempting to accept or
dismiss an already-resolved recommendation raises ``ValueError`` — the
API layer translates that into HTTP 409.

Scope mapping rules:

- ``proposal_section`` — ``scope_id`` is an int-coercible section id.
- ``requirement``      — ``scope_id`` is an int-coercible requirement
                         id; the bound ``proposal_section_id`` (if any)
                         picks the ContributionUnit.
- ``evidence`` / ``gate`` — not convertible; accept raises
                           ``ValueError`` (HTTP 400 upstream).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ContributionUnit,
    ProposalSection,
    RehearsalRecommendation,
    RehearsalRecommendationStatus,
    ReworkAction,
    ReworkStatus,
    TenderRequirement,
)
from app.services.kpi_reason_engine import build_rework_requested_event_payload
from app.services.operational_workflow import ensure_contribution_for_section

logger = logging.getLogger(__name__)


_CONVERTIBLE_SCOPES = {"proposal_section", "requirement"}


@dataclass(slots=True)
class AcceptOverrides:
    """Optional fields that an operator may override at accept time."""

    assigned_to_user_id: int | None = None
    due_at: datetime | None = None
    severity: str | None = None
    is_blocking: bool | None = None
    notes: str | None = None


def _coerce_scope_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"recommendation scope_id {raw!r} is not an int-coercible id",
        ) from exc


async def _resolve_section(
    db: AsyncSession,
    *,
    tender_id: int,
    scope_type: str,
    scope_id: str,
) -> ProposalSection:
    numeric_id = _coerce_scope_id(scope_id)

    if scope_type == "proposal_section":
        section = await db.get(ProposalSection, numeric_id)
        if section is None:
            raise ValueError(f"proposal_section {numeric_id} not found")
        return section

    if scope_type == "requirement":
        requirement = await db.get(TenderRequirement, numeric_id)
        if requirement is None:
            raise ValueError(f"tender_requirement {numeric_id} not found")
        if requirement.tender_id != tender_id:
            raise ValueError(
                f"tender_requirement {numeric_id} belongs to tender "
                f"{requirement.tender_id}, not {tender_id}",
            )
        if not requirement.proposal_section_id:
            raise ValueError(
                f"requirement {numeric_id} is not yet mapped to a proposal section;"
                " cannot create a rework action",
            )
        section = await db.get(ProposalSection, requirement.proposal_section_id)
        if section is None:
            raise ValueError(
                f"proposal_section {requirement.proposal_section_id} "
                "referenced by requirement is missing",
            )
        return section

    raise ValueError(
        f"recommendation scope_type {scope_type!r} is not convertible to a rework action",
    )


async def accept_recommendation(
    db: AsyncSession,
    *,
    recommendation: RehearsalRecommendation,
    tender_id: int,
    actor_id: int | None,
    overrides: AcceptOverrides | None = None,
) -> ReworkAction:
    """Materialise the recommendation as an operational :class:`ReworkAction`.

    The new rework row is linked back via
    ``recommendation.linked_rework_action_id`` and the recommendation is
    flipped to ``ACCEPTED``.  The caller is responsible for committing.
    """

    if recommendation.status != RehearsalRecommendationStatus.PROPOSED:
        raise ValueError(
            f"recommendation {recommendation.id} is already {recommendation.status.value}",
        )
    if recommendation.scope_type not in _CONVERTIBLE_SCOPES:
        raise ValueError(
            f"recommendation {recommendation.id} has scope_type "
            f"{recommendation.scope_type!r} which cannot become a rework action",
        )

    section = await _resolve_section(
        db,
        tender_id=tender_id,
        scope_type=recommendation.scope_type,
        scope_id=recommendation.scope_id,
    )
    contribution = await ensure_contribution_for_section(
        db,
        tender_id=tender_id,
        section=section,
        actor_id=actor_id,
    )

    overrides = overrides or AcceptOverrides()
    severity = (overrides.severity or recommendation.severity or "medium").casefold()
    if severity not in {"high", "medium", "low"}:
        severity = "medium"
    is_blocking = (
        overrides.is_blocking
        if overrides.is_blocking is not None
        else bool(recommendation.is_blocking)
    )
    reason = (
        overrides.notes if overrides.notes else (recommendation.rationale or "")
    ).strip() or "Accepted from rehearsal recommendation."

    rework = ReworkAction(
        contribution_unit_id=contribution.id,
        requested_by=actor_id,
        assigned_to_user_id=overrides.assigned_to_user_id or contribution.owner_user_id,
        severity=severity,
        is_blocking=is_blocking,
        reason=reason,
        due_at=overrides.due_at,
        requested_at=datetime.now(timezone.utc),
        status=ReworkStatus.OPEN,
    )
    db.add(rework)
    await db.flush()

    recommendation.status = RehearsalRecommendationStatus.ACCEPTED
    recommendation.linked_rework_action_id = rework.id
    await db.flush()

    logger.info(
        "rehearsal.recommendation.accepted",
        extra={
            "recommendation_id": recommendation.id,
            "rework_action_id": rework.id,
            "tender_id": tender_id,
            "contribution_id": contribution.id,
        },
    )

    return rework


async def dismiss_recommendation(
    db: AsyncSession,
    *,
    recommendation: RehearsalRecommendation,
    actor_id: int | None,
    reason: str | None = None,
) -> RehearsalRecommendation:
    """Flip ``recommendation`` to ``DISMISSED`` with an optional note."""

    if recommendation.status != RehearsalRecommendationStatus.PROPOSED:
        raise ValueError(
            f"recommendation {recommendation.id} is already {recommendation.status.value}",
        )

    recommendation.status = RehearsalRecommendationStatus.DISMISSED
    if reason:
        existing = recommendation.rationale or ""
        suffix = f"\n[dismissed] {reason.strip()[:500]}"
        recommendation.rationale = (existing + suffix).strip()

    await db.flush()

    logger.info(
        "rehearsal.recommendation.dismissed",
        extra={
            "recommendation_id": recommendation.id,
            "actor_id": actor_id,
            "reason_present": bool(reason),
        },
    )

    return recommendation


def rework_requested_event(
    rework: ReworkAction,
    *,
    contribution: ContributionUnit,
) -> dict[str, Any]:
    """Shim so the API layer can emit a KPI event for ad-hoc creations."""

    return build_rework_requested_event_payload(rework=rework, contribution=contribution)


__all__ = [
    "AcceptOverrides",
    "accept_recommendation",
    "dismiss_recommendation",
    "rework_requested_event",
]
