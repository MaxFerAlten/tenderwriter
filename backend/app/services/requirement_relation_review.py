"""Review queue helpers for inferred requirement relations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import RequirementRelation, RequirementRelationReview

_RELATION_TYPE_RANK = {
    "conflicts_with": 3,
    "overrides": 2,
    "depends_on": 1,
    "parent_of": 1,
}
_ACTIVE_GRAPH_STATE = "active"
_OBSOLETE_GRAPH_STATE = "obsolete"
_ACTION_TO_STATE = {
    "approve": "approved",
    "request_changes": "changes_requested",
    "reset_to_pending": "pending",
    "edit": "pending",
    "dismiss": "dismissed",
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


def _snapshot_relation(relation: RequirementRelation) -> dict[str, Any]:
    return {
        "id": relation.id,
        "source_requirement_id": relation.source_requirement_id,
        "target_requirement_id": relation.target_requirement_id,
        "relation_type": relation.relation_type,
        "confidence": relation.confidence,
        "review_state": relation.review_state,
        "graph_state": relation.graph_state,
    }


def _normalize_relation_type(value: Any, fallback: str | None = None) -> str:
    relation_type = str(value or fallback or "").strip().casefold()
    if relation_type not in {"overrides", "depends_on", "parent_of", "conflicts_with"}:
        raise ValueError(f"Unsupported relation type: {value!r}")
    return relation_type


def _apply_relation_edit(
    relation: RequirementRelation,
    edit_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in dict(edit_payload or {}).items()
        if key
        in {
            "source_requirement_id",
            "target_requirement_id",
            "relation_type",
            "confidence",
        }
        and value is not None
    }
    if not payload:
        raise ValueError("Edit action requires at least one relation field.")

    before = _snapshot_relation(relation)
    source_requirement_id = int(
        payload.get("source_requirement_id") or relation.source_requirement_id
    )
    target_requirement_id = int(
        payload.get("target_requirement_id") or relation.target_requirement_id
    )
    if source_requirement_id == target_requirement_id:
        raise ValueError("Relation source and target requirements must be different.")

    relation.source_requirement_id = source_requirement_id
    relation.target_requirement_id = target_requirement_id
    if "relation_type" in payload:
        relation.relation_type = _normalize_relation_type(
            payload["relation_type"], relation.relation_type
        )
    if "confidence" in payload:
        confidence = float(payload["confidence"])
        relation.confidence = max(0.0, min(confidence, 1.0))

    return {
        "before": before,
        "after": _snapshot_relation(relation),
        "fields": sorted(payload),
    }


def _merge_relation_metadata(
    relation: RequirementRelation,
    *,
    latest_action: dict[str, Any],
) -> None:
    metadata_json = dict(relation.metadata_json or {})
    history = list(metadata_json.get("editorial_actions") or [])
    history.append(latest_action)
    metadata_json["editorial_actions"] = history[-20:]
    metadata_json["latest_editorial_action"] = latest_action
    relation.metadata_json = metadata_json


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
    edit_payload: dict[str, Any] | None = None,
) -> tuple[RequirementRelation, RequirementRelationReview]:
    """Apply a review action to an inferred requirement relation."""

    normalized_action = _normalize_review_action(action)
    previous_state = str(relation.review_state or "pending")
    previous_graph_state = str(relation.graph_state or _ACTIVE_GRAPH_STATE)
    new_state = _ACTION_TO_STATE[normalized_action]
    action_metadata = {
        **dict(metadata or {}),
        "previous_graph_state": previous_graph_state,
    }

    if normalized_action == "edit":
        action_metadata["edit"] = _apply_relation_edit(relation, edit_payload)
    elif normalized_action == "dismiss":
        relation.graph_state = _OBSOLETE_GRAPH_STATE
        action_metadata["lifecycle"] = {
            "graph_state": _OBSOLETE_GRAPH_STATE,
            "reason": "manual_dismissed",
            "previous_graph_state": previous_graph_state,
        }
        relation.metadata_json = {
            **dict(relation.metadata_json or {}),
            "lifecycle": action_metadata["lifecycle"],
        }

    review = RequirementRelationReview(
        tender_id=relation.tender_id,
        requirement_relation_id=relation.id,
        actor_id=actor_id,
        action=normalized_action,
        previous_review_state=previous_state,
        new_review_state=new_state,
        notes=str(notes).strip() if notes else None,
        metadata_json=action_metadata,
    )
    db.add(review)

    relation.review_state = new_state
    if normalized_action in {"edit", "dismiss"}:
        _merge_relation_metadata(
            relation,
            latest_action={
                "action": normalized_action,
                "previous_review_state": previous_state,
                "new_review_state": new_state,
                "previous_graph_state": previous_graph_state,
                "graph_state": relation.graph_state,
                "actor_id": actor_id,
            },
        )
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
