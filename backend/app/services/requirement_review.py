"""Review queue helpers for consolidated requirements."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsolidatedRequirement, RequirementReview


_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
_ACTIVE_GRAPH_STATE = "active"
_ACTION_TO_STATE = {
    "approve": "approved",
    "request_changes": "changes_requested",
    "reset_to_pending": "pending",
}


def _normalize_review_action(value: Any) -> str:
    action = str(value or "").strip().casefold()
    if action not in _ACTION_TO_STATE:
        raise ValueError(f"Unsupported review action: {value!r}")
    return action


def _normalize_review_state_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if not normalized:
        return None
    return normalized


async def get_consolidated_requirement_for_tender(
    db: AsyncSession,
    *,
    tender_id: int,
    requirement_id: int,
) -> ConsolidatedRequirement | None:
    """Load a consolidated requirement scoped to a tender."""

    result = await db.execute(
        select(ConsolidatedRequirement).where(
            ConsolidatedRequirement.tender_id == tender_id,
            ConsolidatedRequirement.id == requirement_id,
            ConsolidatedRequirement.graph_state == _ACTIVE_GRAPH_STATE,
        )
    )
    return result.scalar_one_or_none()


async def list_consolidated_requirements_for_review(
    db: AsyncSession,
    *,
    tender_id: int,
    review_state: str | None = "pending",
    limit: int = 50,
) -> list[ConsolidatedRequirement]:
    """Return consolidated requirements ordered for review triage."""

    normalized_limit = max(1, min(int(limit), 100))
    normalized_state = _normalize_review_state_filter(review_state)
    statement = select(ConsolidatedRequirement).where(
        ConsolidatedRequirement.tender_id == tender_id,
        ConsolidatedRequirement.graph_state == _ACTIVE_GRAPH_STATE,
    )
    if normalized_state is not None:
        statement = statement.where(ConsolidatedRequirement.review_state == normalized_state)

    result = await db.execute(statement)
    requirements = list(result.scalars().all())
    requirements.sort(
        key=lambda requirement: (
            -_PRIORITY_RANK.get(str(requirement.priority or "medium").casefold(), 2),
            requirement.confidence if requirement.confidence is not None else 999.0,
            -(requirement.id or 0),
        )
    )
    return requirements[:normalized_limit]


async def apply_requirement_review(
    db: AsyncSession,
    *,
    requirement: ConsolidatedRequirement,
    actor_id: int | None,
    action: str,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[ConsolidatedRequirement, RequirementReview]:
    """Apply a review action to a consolidated requirement and persist its audit entry."""

    normalized_action = _normalize_review_action(action)
    previous_state = str(requirement.review_state or "pending")
    new_state = _ACTION_TO_STATE[normalized_action]

    review = RequirementReview(
        tender_id=requirement.tender_id,
        consolidated_requirement_id=requirement.id,
        actor_id=actor_id,
        action=normalized_action,
        previous_review_state=previous_state,
        new_review_state=new_state,
        notes=str(notes).strip() if notes else None,
        metadata_json=dict(metadata or {}),
    )
    db.add(review)

    requirement.review_state = new_state
    review_count = int((requirement.metadata_json or {}).get("review_count") or 0) + 1
    requirement.metadata_json = {
        **dict(requirement.metadata_json or {}),
        "review_count": review_count,
        "latest_review": {
            "action": normalized_action,
            "previous_review_state": previous_state,
            "new_review_state": new_state,
            "actor_id": actor_id,
            "notes": str(notes).strip() if notes else None,
        },
    }

    await db.flush()
    return requirement, review
