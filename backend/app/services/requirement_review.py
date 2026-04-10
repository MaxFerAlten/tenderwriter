"""Review queue helpers for consolidated requirements."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsolidatedRequirement, RequirementReview
from app.services.tender_requirements import normalize_requirement_text


_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
_ACTIVE_GRAPH_STATE = "active"
_OBSOLETE_GRAPH_STATE = "obsolete"
_ACTION_TO_STATE = {
    "approve": "approved",
    "request_changes": "changes_requested",
    "reset_to_pending": "pending",
    "edit": "pending",
    "dismiss": "dismissed",
    "merge": "merged",
    "split": "split",
}
_EDITABLE_FIELDS = {
    "canonical_text",
    "category",
    "priority",
    "parent_requirement_key",
    "applicability",
    "conditions",
    "exceptions",
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


def _clean_text(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _clean_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list | tuple | set) else [value]
    cleaned: list[str] = []
    for item in values:
        text = _clean_text(item)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _clean_priority(value: Any, fallback: str | None = None) -> str:
    priority = str(value or fallback or "medium").strip().casefold()
    return priority if priority in _PRIORITY_RANK else "medium"


def _snapshot_requirement(requirement: ConsolidatedRequirement) -> dict[str, Any]:
    return {
        "id": requirement.id,
        "canonical_text": requirement.canonical_text,
        "normalized_text": requirement.normalized_text,
        "category": requirement.category,
        "priority": requirement.priority,
        "review_state": requirement.review_state,
        "graph_state": requirement.graph_state,
        "parent_requirement_id": requirement.parent_requirement_id,
        "parent_requirement_key": requirement.parent_requirement_key,
        "applicability": dict(requirement.applicability or {}),
        "conditions": list(requirement.conditions or []),
        "exceptions": list(requirement.exceptions or []),
    }


def _merge_requirement_metadata(
    requirement: ConsolidatedRequirement,
    *,
    latest_action: dict[str, Any],
    action_history_key: str = "editorial_actions",
) -> None:
    metadata_json = dict(requirement.metadata_json or {})
    history = list(metadata_json.get(action_history_key) or [])
    history.append(latest_action)
    metadata_json[action_history_key] = history[-20:]
    metadata_json["latest_editorial_action"] = latest_action
    requirement.metadata_json = metadata_json


def _apply_requirement_edit(
    requirement: ConsolidatedRequirement,
    edit_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in dict(edit_payload or {}).items()
        if key in _EDITABLE_FIELDS and value is not None
    }
    if not payload:
        raise ValueError("Edit action requires at least one editable field.")

    before = _snapshot_requirement(requirement)

    if "canonical_text" in payload:
        canonical_text = _clean_text(payload["canonical_text"])
        if not canonical_text:
            raise ValueError("Edited canonical_text cannot be empty.")
        requirement.canonical_text = canonical_text
        requirement.normalized_text = normalize_requirement_text(canonical_text)

    if "category" in payload:
        requirement.category = _clean_text(payload["category"])
    if "priority" in payload:
        requirement.priority = _clean_priority(payload["priority"], requirement.priority)
    if "parent_requirement_key" in payload:
        requirement.parent_requirement_key = _clean_text(payload["parent_requirement_key"])
        requirement.parent_requirement_id = None
    if "applicability" in payload:
        applicability = payload["applicability"]
        requirement.applicability = dict(applicability) if isinstance(applicability, dict) else {}
    if "conditions" in payload:
        requirement.conditions = _clean_text_list(payload["conditions"])
    if "exceptions" in payload:
        requirement.exceptions = _clean_text_list(payload["exceptions"])

    return {
        "before": before,
        "after": _snapshot_requirement(requirement),
        "fields": sorted(payload),
    }


def _mark_requirement_obsolete(
    requirement: ConsolidatedRequirement,
    *,
    reason: str,
    metadata: dict[str, Any],
) -> None:
    requirement.graph_state = _OBSOLETE_GRAPH_STATE
    lifecycle = {
        "graph_state": _OBSOLETE_GRAPH_STATE,
        "reason": reason,
        "previous_graph_state": metadata.get("previous_graph_state"),
    }
    requirement.metadata_json = {
        **dict(requirement.metadata_json or {}),
        "lifecycle": lifecycle,
    }


def _build_split_requirement(
    requirement: ConsolidatedRequirement,
    payload: dict[str, Any],
    *,
    actor_id: int | None,
) -> ConsolidatedRequirement:
    canonical_text = _clean_text(payload.get("canonical_text") or payload.get("text"))
    if not canonical_text:
        raise ValueError("Split requirements must include canonical_text.")

    return ConsolidatedRequirement(
        tender_id=requirement.tender_id,
        canonical_text=canonical_text,
        normalized_text=normalize_requirement_text(canonical_text),
        category=_clean_text(payload.get("category")) or requirement.category,
        priority=_clean_priority(payload.get("priority"), requirement.priority),
        confidence=payload.get("confidence"),
        source_count=1,
        consolidation_method="manual_split_v1",
        review_state="pending",
        graph_state=_ACTIVE_GRAPH_STATE,
        parent_requirement_id=requirement.parent_requirement_id,
        parent_requirement_key=_clean_text(payload.get("parent_requirement_key"))
        or requirement.parent_requirement_key,
        applicability=dict(payload.get("applicability") or requirement.applicability or {}),
        conditions=_clean_text_list(payload.get("conditions") or requirement.conditions),
        exceptions=_clean_text_list(payload.get("exceptions") or requirement.exceptions),
        metadata_json={
            "manual_editorial": {
                "action": "split_child",
                "split_from_requirement_id": requirement.id,
                "actor_id": actor_id,
            }
        },
    )


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
    edit_payload: dict[str, Any] | None = None,
    target_requirement: ConsolidatedRequirement | None = None,
    split_payloads: list[dict[str, Any]] | None = None,
) -> tuple[ConsolidatedRequirement, RequirementReview]:
    """Apply a review action to a consolidated requirement and persist its audit entry."""

    normalized_action = _normalize_review_action(action)
    previous_state = str(requirement.review_state or "pending")
    previous_graph_state = str(requirement.graph_state or _ACTIVE_GRAPH_STATE)
    new_state = _ACTION_TO_STATE[normalized_action]
    action_metadata = {
        **dict(metadata or {}),
        "previous_graph_state": previous_graph_state,
    }
    created_requirements: list[ConsolidatedRequirement] = []

    if normalized_action == "edit":
        action_metadata["edit"] = _apply_requirement_edit(requirement, edit_payload)
    elif normalized_action == "dismiss":
        _mark_requirement_obsolete(
            requirement,
            reason="manual_dismissed",
            metadata=action_metadata,
        )
    elif normalized_action == "merge":
        if target_requirement is None or target_requirement.id == requirement.id:
            raise ValueError("Merge action requires a different target requirement.")
        target_metadata = dict(target_requirement.metadata_json or {})
        manual_merges = list(target_metadata.get("manual_merges") or [])
        manual_merges.append(
            {
                "source_requirement_id": requirement.id,
                "source_requirement_text": requirement.canonical_text,
                "actor_id": actor_id,
            }
        )
        target_metadata["manual_merges"] = manual_merges[-20:]
        target_metadata["latest_editorial_action"] = {
            "action": "merge_target",
            "source_requirement_id": requirement.id,
            "actor_id": actor_id,
        }
        target_requirement.metadata_json = target_metadata
        target_requirement.source_count = int(target_requirement.source_count or 0) + int(
            requirement.source_count or 0
        )
        action_metadata["merge_target"] = _snapshot_requirement(target_requirement)
        _mark_requirement_obsolete(
            requirement,
            reason="manual_merged",
            metadata=action_metadata,
        )
    elif normalized_action == "split":
        split_payloads = list(split_payloads or [])
        if len(split_payloads) < 2:
            raise ValueError("Split action requires at least two replacement requirements.")
        created_requirements = [
            _build_split_requirement(requirement, payload, actor_id=actor_id)
            for payload in split_payloads
        ]
        for created_requirement in created_requirements:
            db.add(created_requirement)
        action_metadata["split_children"] = [
            {
                "canonical_text": item.canonical_text,
                "normalized_text": item.normalized_text,
            }
            for item in created_requirements
        ]
        _mark_requirement_obsolete(
            requirement,
            reason="manual_split",
            metadata=action_metadata,
        )

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
    if normalized_action in {"edit", "dismiss", "merge", "split"}:
        _merge_requirement_metadata(
            requirement,
            latest_action={
                "action": normalized_action,
                "previous_review_state": previous_state,
                "new_review_state": new_state,
                "previous_graph_state": previous_graph_state,
                "graph_state": requirement.graph_state,
                "actor_id": actor_id,
            },
        )

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
    review.metadata_json = action_metadata

    await db.flush()
    if normalized_action == "split":
        split_children = list(action_metadata.get("split_children") or [])
        created_ids = [getattr(instance, "id", None) for instance in created_requirements]
        for child, created_id in zip(split_children, created_ids, strict=False):
            child["id"] = created_id
        review.metadata_json = {
            **dict(review.metadata_json or {}),
            "split_children": split_children,
        }
        await db.flush()
    return requirement, review
