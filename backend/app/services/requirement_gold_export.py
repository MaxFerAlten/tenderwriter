"""Export reviewed requirement graphs as draft evaluation gold sets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ConsolidatedRequirement, RequirementRelation, Tender
from app.services.requirement_evaluation import GOLD_SET_SCHEMA_VERSION


_ACTIVE_GRAPH_STATE = "active"
_APPROVED_REVIEW_STATES = {"approved", "accepted", "verified"}


@dataclass(frozen=True)
class RequirementGoldExportOptions:
    name: str = "requirement-evaluation-draft"
    description: str = (
        "Draft requirement evaluation gold set exported from reviewed consolidated requirements."
    )
    include_pending_predictions: bool = True
    include_negative_cases: bool = True


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


def _review_state(value: Any) -> str:
    return str(value or "pending").strip().casefold()


def _graph_state(value: Any) -> str:
    return str(value or _ACTIVE_GRAPH_STATE).strip().casefold()


def _is_active_requirement(requirement: Any) -> bool:
    return _graph_state(getattr(requirement, "graph_state", None)) == _ACTIVE_GRAPH_STATE


def _is_approved_requirement(requirement: Any) -> bool:
    return _review_state(getattr(requirement, "review_state", None)) in _APPROVED_REVIEW_STATES


def _is_active_relation(relation: Any) -> bool:
    return _graph_state(getattr(relation, "graph_state", None)) == _ACTIVE_GRAPH_STATE


def _is_approved_relation(relation: Any) -> bool:
    return _review_state(getattr(relation, "review_state", None)) in _APPROVED_REVIEW_STATES


def _metadata(value: Any) -> Mapping[str, Any]:
    metadata_json = getattr(value, "metadata_json", None)
    return metadata_json if isinstance(metadata_json, Mapping) else {}


def _source_citations(requirement: Any) -> list[dict[str, Any]]:
    metadata_json = _metadata(requirement)
    citations: list[dict[str, Any]] = []
    for source in metadata_json.get("sources") or []:
        if not isinstance(source, Mapping):
            continue
        citation = {
            "quote": source.get("summary_text") or getattr(requirement, "canonical_text", None),
            "source_reference": source.get("source_reference"),
            "source_document_ref": source.get("source_document_ref"),
            "filename": source.get("filename"),
            "document_role": source.get("document_role"),
        }
        citations.append({key: value for key, value in citation.items() if value not in (None, "", [], {})})
    return citations


def _requirement_payload(requirement: Any, *, expected: bool) -> dict[str, Any]:
    canonical_text = str(getattr(requirement, "canonical_text", "") or "").strip()
    payload: dict[str, Any] = {
        "key": f"consolidated-{getattr(requirement, 'id', 'draft')}",
        "category": getattr(requirement, "category", None),
        "priority": getattr(requirement, "priority", None) or "medium",
        "review_state": getattr(requirement, "review_state", None) or "pending",
        "source_count": int(getattr(requirement, "source_count", 0) or 0),
        "citations": _source_citations(requirement),
    }
    if expected:
        payload["text"] = canonical_text
    else:
        payload["canonical_text"] = canonical_text
        payload["confidence"] = getattr(requirement, "confidence", None)
    for attr in ("applicability", "conditions", "exceptions", "parent_requirement_key"):
        value = getattr(requirement, attr, None)
        if value not in (None, "", [], {}):
            payload[attr] = value
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _relation_endpoint_text(relation: Any, endpoint: str) -> str:
    requirement = getattr(relation, f"{endpoint}_requirement", None)
    if requirement is None:
        return ""
    return str(getattr(requirement, "canonical_text", None) or "").strip()


def _relation_payload(relation: Any, *, expected: bool) -> dict[str, Any]:
    source_text = _relation_endpoint_text(relation, "source")
    target_text = _relation_endpoint_text(relation, "target")
    payload: dict[str, Any] = {
        "relation_type": str(getattr(relation, "relation_type", "") or "").strip().casefold(),
        "review_state": getattr(relation, "review_state", None) or "pending",
    }
    if expected:
        payload["source_text"] = source_text
        payload["target_text"] = target_text
    else:
        payload["source_requirement_text"] = source_text
        payload["target_requirement_text"] = target_text
        payload["confidence"] = getattr(relation, "confidence", None)
    metadata_json = _metadata(relation)
    if metadata_json:
        payload["metadata_json"] = dict(metadata_json)
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def build_requirement_gold_set_case(
    tender: Any,
    requirements: Sequence[Any],
    relations: Sequence[Any],
    *,
    include_pending_predictions: bool = True,
) -> dict[str, Any]:
    """Build one evaluator case from a reviewed tender graph."""

    active_requirements = [item for item in requirements if _is_active_requirement(item)]
    expected_requirements = [item for item in active_requirements if _is_approved_requirement(item)]
    predicted_requirements = (
        active_requirements
        if include_pending_predictions
        else [item for item in active_requirements if _is_approved_requirement(item)]
    )

    active_requirement_ids = {
        int(getattr(requirement, "id"))
        for requirement in active_requirements
        if getattr(requirement, "id", None) is not None
    }
    approved_requirement_ids = {
        int(getattr(requirement, "id"))
        for requirement in expected_requirements
        if getattr(requirement, "id", None) is not None
    }
    active_relations = [
        relation
        for relation in relations
        if _is_active_relation(relation)
        and int(getattr(relation, "source_requirement_id", 0) or 0) in active_requirement_ids
        and int(getattr(relation, "target_requirement_id", 0) or 0) in active_requirement_ids
    ]
    expected_relations = [
        relation
        for relation in active_relations
        if _is_approved_relation(relation)
        and int(getattr(relation, "source_requirement_id", 0) or 0) in approved_requirement_ids
        and int(getattr(relation, "target_requirement_id", 0) or 0) in approved_requirement_ids
    ]
    predicted_relations = (
        active_relations
        if include_pending_predictions
        else [item for item in active_relations if _is_approved_relation(item)]
    )

    tender_id = int(getattr(tender, "id", 0) or 0)
    title = str(getattr(tender, "title", "") or f"tender-{tender_id}").strip()
    negative_case = not expected_requirements and not expected_relations
    return {
        "id": f"tender-{tender_id}",
        "tender_id": tender_id,
        "title": title,
        "draft_review_required": True,
        "negative_case": negative_case,
        "expected_requirements": [
            _requirement_payload(requirement, expected=True)
            for requirement in expected_requirements
        ],
        "predicted_requirements": [
            _requirement_payload(requirement, expected=False)
            for requirement in predicted_requirements
        ],
        "expected_relations": [
            _relation_payload(relation, expected=True)
            for relation in expected_relations
        ],
        "predicted_relations": [
            _relation_payload(relation, expected=False)
            for relation in predicted_relations
        ],
    }


def build_requirement_gold_set_payload(
    cases: Sequence[Mapping[str, Any]],
    *,
    options: RequirementGoldExportOptions | None = None,
) -> dict[str, Any]:
    """Wrap draft gold-set cases in the evaluator envelope."""

    options = options or RequirementGoldExportOptions()
    return {
        "schema_version": GOLD_SET_SCHEMA_VERSION,
        "name": options.name,
        "description": options.description,
        "metadata": {
            "exporter": "requirement_gold_export_v1",
            "draft_review_required": True,
            "include_negative_cases": options.include_negative_cases,
            "expected_source": "approved_consolidated_requirements",
            "predicted_source": (
                "active_consolidated_requirements"
                if options.include_pending_predictions
                else "approved_consolidated_requirements"
            ),
        },
        "cases": list(cases),
    }


async def list_requirement_gold_export_tender_ids(
    db: AsyncSession,
    *,
    tender_ids: Iterable[int] | None = None,
) -> list[int]:
    """Return tender ids that can be exported into draft gold-set cases."""

    if tender_ids is not None:
        return _normalize_tender_ids(tender_ids)

    result = await db.execute(
        select(ConsolidatedRequirement.tender_id)
        .where(ConsolidatedRequirement.graph_state == _ACTIVE_GRAPH_STATE)
        .distinct()
        .order_by(ConsolidatedRequirement.tender_id.asc())
    )
    return _normalize_tender_ids(result.scalars().all())


async def export_requirement_gold_set_payload(
    db: AsyncSession,
    *,
    tender_ids: Iterable[int] | None = None,
    options: RequirementGoldExportOptions | None = None,
) -> dict[str, Any]:
    """Load reviewed requirement graphs and export a draft evaluator payload."""

    options = options or RequirementGoldExportOptions()
    resolved_tender_ids = await list_requirement_gold_export_tender_ids(
        db,
        tender_ids=tender_ids,
    )
    cases: list[dict[str, Any]] = []
    for tender_id in resolved_tender_ids:
        tender_result = await db.execute(select(Tender).where(Tender.id == tender_id))
        tender = tender_result.scalar_one_or_none()
        if tender is None:
            continue

        requirement_result = await db.execute(
            select(ConsolidatedRequirement)
            .where(
                ConsolidatedRequirement.tender_id == tender_id,
                ConsolidatedRequirement.graph_state == _ACTIVE_GRAPH_STATE,
            )
            .order_by(ConsolidatedRequirement.id.asc())
        )
        requirements = list(requirement_result.scalars().all())
        relation_result = await db.execute(
            select(RequirementRelation)
            .where(
                RequirementRelation.tender_id == tender_id,
                RequirementRelation.graph_state == _ACTIVE_GRAPH_STATE,
            )
            .options(
                selectinload(RequirementRelation.source_requirement),
                selectinload(RequirementRelation.target_requirement),
            )
            .order_by(RequirementRelation.id.asc())
        )
        relations = list(relation_result.scalars().all())
        case = build_requirement_gold_set_case(
            tender,
            requirements,
            relations,
            include_pending_predictions=options.include_pending_predictions,
        )
        if (
            case["expected_requirements"]
            or case["expected_relations"]
            or (
                options.include_negative_cases
                and (case["predicted_requirements"] or case["predicted_relations"] or tender_ids is not None)
            )
        ):
            cases.append(case)

    return build_requirement_gold_set_payload(cases, options=options)
