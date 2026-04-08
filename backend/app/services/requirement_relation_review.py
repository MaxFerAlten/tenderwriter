"""Review queue helpers for inferred requirement relations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RequirementRelation, RequirementRelationReview


_RELATION_TYPE_RANK = {
    "overrides": 2,
    "depends_on": 1,
}
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


def _normalize_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if not normalized:
        return None
    return normalized


async def get_requirement_relation_for_tender(
    db: AsyncSession,
    *,
    tender_id: int,
    relation_id: int,
) -> RequirementRelation | None:
    """Load an inferred requirement relation scoped to a tender."""

    result = await db.execute(
        select(RequirementRelation)
        .where(
            RequirementRelation.tender_id == tender_id,
            RequirementRelation.id == relation_id,
            RequirementRelation.graph_state == _ACTIVE_GRAPH_STATE,
        )
        .options(
            selectinload(RequirementRelation.source_requirement),
            selectinload(RequirementRelation.target_requirement),
        )
    )
    return result.scalar_one_or_none()


async def list_requirement_relations_for_review(
    db: AsyncSession,
    *,
    tender_id: int,
    review_state: str | None = "pending",
    relation_type: str | None = None,
    limit: int = 50,
) -> list[RequirementRelation]:
    """Return inferred relations ordered for review triage."""

    normalized_limit = max(1, min(int(limit), 100))
    normalized_state = _normalize_filter_value(review_state)
    normalized_relation_type = _normalize_filter_value(relation_type)

    statement = (
        select(RequirementRelation)
        .where(
            RequirementRelation.tender_id == tender_id,
            RequirementRelation.graph_state == _ACTIVE_GRAPH_STATE,
        )
        .options(
            selectinload(RequirementRelation.source_requirement),
            selectinload(RequirementRelation.target_requirement),
        )
    )
    if normalized_state is not None:
        statement = statement.where(RequirementRelation.review_state == normalized_state)
    if normalized_relation_type is not None:
        statement = statement.where(RequirementRelation.relation_type == normalized_relation_type)

    result = await db.execute(statement)
    relations = list(result.scalars().all())
    relations.sort(
        key=lambda relation: (
            -_RELATION_TYPE_RANK.get(str(relation.relation_type or "").casefold(), 0),
            relation.confidence if relation.confidence is not None else 999.0,
            -(relation.id or 0),
        )
    )
    return relations[:normalized_limit]


async def apply_requirement_relation_review(
    db: AsyncSession,
    *,
    relation: RequirementRelation,
    actor_id: int | None,
    action: str,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[RequirementRelation, RequirementRelationReview]:
    """Apply a review action to an inferred requirement relation."""

    normalized_action = _normalize_review_action(action)
    previous_state = str(relation.review_state or "pending")
    new_state = _ACTION_TO_STATE[normalized_action]

    review = RequirementRelationReview(
        tender_id=relation.tender_id,
        requirement_relation_id=relation.id,
        actor_id=actor_id,
        action=normalized_action,
        previous_review_state=previous_state,
        new_review_state=new_state,
        notes=str(notes).strip() if notes else None,
        metadata_json=dict(metadata or {}),
    )
    db.add(review)

    relation.review_state = new_state
    review_count = int((relation.metadata_json or {}).get("review_count") or 0) + 1
    relation.metadata_json = {
        **dict(relation.metadata_json or {}),
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
    return relation, review
