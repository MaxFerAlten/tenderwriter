"""Internal client and publisher helpers for tw-kpi-reason-engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import (
    KpiDomainEvent,
    KpiEventDeliveryStatus,
    Proposal,
    ProposalSection,
    Tender,
    TenderRequirement,
)

logger = structlog.get_logger()
_EVENT_SCHEMA_VERSION = "1.0.0"


@dataclass(slots=True)
class KpiClientResult:
    """Normalized result for outbound KPI service requests."""

    delivered: bool
    status_code: int | None
    response_json: dict[str, Any]
    error_message: str | None = None


class KpiReasonEngineClient:
    """HTTP client for the internal KPI reason engine service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_token: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.kpi_reason_engine_base_url or "").rstrip("/")
        self.service_token = service_token if service_token is not None else settings.kpi_reason_engine_service_token
        self.timeout = timeout if timeout is not None else settings.kpi_reason_engine_timeout
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        token = (self.service_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Service-Token"] = token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> KpiClientResult:
        if not self.base_url:
            return KpiClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message="KPI reason engine base URL is not configured.",
            )

        request_kwargs: dict[str, Any] = {"headers": self._headers()}
        if payload is not None:
            request_kwargs["json"] = payload

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, **request_kwargs)
        except httpx.HTTPError as exc:
            return KpiClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message=str(exc),
            )

        response_json = _safe_response_json(response)
        delivered = 200 <= response.status_code < 300
        error_message = None if delivered else f"KPI service returned HTTP {response.status_code}"
        return KpiClientResult(
            delivered=delivered,
            status_code=response.status_code,
            response_json=response_json,
            error_message=error_message,
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> KpiClientResult:
        return await self._request("POST", path, payload)

    async def _get(self, path: str) -> KpiClientResult:
        return await self._request("GET", path)

    async def sync_tender(self, payload: dict[str, Any]) -> KpiClientResult:
        return await self._post("/v1/tenders", payload)

    async def publish_event(
        self,
        external_tender_id: str,
        payload: dict[str, Any],
    ) -> KpiClientResult:
        return await self._post(f"/v1/tenders/{external_tender_id}/events", payload)

    async def get_portfolio_overview(self) -> KpiClientResult:
        return await self._get("/v1/admin/portfolio/overview")

    async def get_portfolio_bottlenecks(self) -> KpiClientResult:
        return await self._get("/v1/admin/portfolio/bottlenecks")

    async def get_tender_snapshot(self, external_tender_id: str) -> KpiClientResult:
        return await self._get(f"/v1/tenders/{external_tender_id}/snapshot")

    async def get_tender_diagnostics(self, external_tender_id: str) -> KpiClientResult:
        return await self._get(f"/v1/tenders/{external_tender_id}/diagnostics")

    async def get_tender_transitions(self, external_tender_id: str) -> KpiClientResult:
        return await self._get(f"/v1/tenders/{external_tender_id}/transitions")

    async def get_tender_forecast(self, external_tender_id: str) -> KpiClientResult:
        return await self._get(f"/v1/tenders/{external_tender_id}/forecast")


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return {"raw_text": text} if text else {}

    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_to_iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def select_primary_proposal(proposals: Sequence[Proposal] | None) -> Proposal | None:
    """Pick the most relevant proposal for KPI snapshot sync."""

    if not proposals:
        return None

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return max(
        proposals,
        key=lambda item: (
            item.version or 0,
            _as_utc(item.created_at) or epoch,
            item.id or 0,
        ),
    )


def build_tender_sync_payload(tender: Tender) -> dict[str, Any]:
    """Build the canonical tender sync payload expected by the KPI service."""

    proposal = select_primary_proposal(list(tender.proposals or []))
    sections = sorted(
        list(proposal.sections or []) if proposal else [],
        key=lambda item: ((item.order or 0), item.id or 0),
    )
    requirements = sorted(
        list(tender.requirements or []),
        key=lambda item: item.id or 0,
    )

    return {
        "external_tender_id": str(tender.id),
        "title": tender.title,
        "customer_name": tender.client,
        "due_at": _datetime_to_iso(tender.deadline),
        "current_status": _enum_value(tender.status),
        "departments": [],
        "requirement_contexts": [
            _compact_dict(
                {
                    "external_requirement_id": str(requirement.id),
                    "reference": requirement.category,
                    "summary": requirement.requirement_text,
                    "priority": requirement.priority,
                    "compliance_status": _enum_value(requirement.compliance_status),
                    "mapped_section_id": str(requirement.proposal_section_id) if requirement.proposal_section_id else None,
                }
            )
            for requirement in requirements
        ],
        "section_contexts": [
            _compact_dict(
                {
                    "external_section_id": str(section.id),
                    "title": section.title,
                    "owner_department": None,
                    "status": _enum_value(section.status),
                }
            )
            for section in sections
        ],
        "metadata": _compact_dict(
            {
                "description": tender.description,
                "category": tender.category,
                "tags": list(tender.tags or []),
                "budget_estimate": tender.budget_estimate,
                "source_file_url": tender.source_file_url,
                "proposal_id": proposal.id if proposal else None,
            }
        ),
    }


def build_domain_event_payload(
    *,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any],
    actor_id: int | None = None,
    source: str = "tw-backend",
) -> dict[str, Any]:
    """Build the canonical event envelope expected by the KPI service."""

    return _compact_dict(
        {
            "event_type": event_type,
            "occurred_at": _datetime_to_iso(occurred_at),
            "actor_id": str(actor_id) if actor_id is not None else None,
            "source": source,
            "schema_version": _EVENT_SCHEMA_VERSION,
            "payload": payload,
        }
    )


def build_tender_created_event_payload(tender: Tender) -> dict[str, Any]:
    return _compact_dict(
        {
            "title": tender.title,
            "customer_name": tender.client,
            "due_at": _datetime_to_iso(tender.deadline),
            "status": _enum_value(tender.status),
        }
    )


def build_tender_document_ingested_event_payload(
    *,
    document_id: str,
    filename: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    return _compact_dict(
        {
            "document_id": document_id,
            "document_type": "tender",
            "filename": filename,
            "ingestion_status": stats.get("status"),
            "chunks": stats.get("chunks"),
            "entities": stats.get("entities"),
        }
    )


def build_requirements_extracted_event_payload(
    *,
    document_id: str,
    filename: str,
    extracted_candidates: Sequence[dict[str, Any]],
    created_requirements: Sequence[TenderRequirement],
) -> dict[str, Any]:
    priority_breakdown: dict[str, int] = {}
    references: list[str] = []
    sample_requirements: list[str] = []
    for candidate in extracted_candidates:
        priority = str(candidate.get("priority") or "medium").strip().casefold()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        priority_breakdown[priority] = priority_breakdown.get(priority, 0) + 1

        reference = candidate.get("reference") or candidate.get("section") or candidate.get("source_section")
        if reference is not None:
            references.append(str(reference))

        summary = str(candidate.get("summary") or "").strip()
        if summary and len(sample_requirements) < 5:
            sample_requirements.append(summary)

    unique_references = list(dict.fromkeys(references))
    return _compact_dict(
        {
            "document_id": document_id,
            "document_type": "tender",
            "filename": filename,
            "requirement_count": len(extracted_candidates),
            "new_requirement_count": len(created_requirements),
            "created_requirement_ids": [
                str(requirement.id) for requirement in created_requirements if getattr(requirement, "id", None) is not None
            ],
            "priority_breakdown": priority_breakdown,
            "references": unique_references[:10],
            "sample_requirements": sample_requirements,
            "extraction_method": "heuristic_v1",
        }
    )


def build_proposal_created_event_payload(*, proposal: Proposal, section_count: int) -> dict[str, Any]:
    return {
        "proposal_id": proposal.id,
        "section_count": section_count,
        "status": _enum_value(proposal.status),
    }


def build_proposal_section_updated_event_payload(
    *,
    section: ProposalSection,
    change_type: str,
    changed_fields: Sequence[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_section_id": str(section.id),
            "change_type": change_type,
            "changed_fields": list(changed_fields or []),
            "status": _enum_value(section.status),
            "assigned_to": section.assigned_to,
            "title": section.title,
            "source": source,
        }
    )


def build_tender_submitted_event_payload(*, submitted_at: datetime, channel: str) -> dict[str, Any]:
    return {
        "submitted_at": _datetime_to_iso(submitted_at),
        "channel": channel,
    }


def build_tender_outcome_recorded_event_payload(*, outcome: str, recorded_at: datetime) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "recorded_at": _datetime_to_iso(recorded_at),
    }


def _duration_hours(start: datetime | None, end: datetime | None) -> float | None:
    normalized_start = _as_utc(start)
    normalized_end = _as_utc(end)
    if normalized_start is None or normalized_end is None:
        return None
    return round((normalized_end - normalized_start).total_seconds() / 3600, 2)


def build_contribution_request_created_event_payload(
    *,
    request: ContributionRequest,
    contribution: ContributionUnit,
) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_request_id": str(request.id),
            "title": contribution.title,
            "department_name": contribution.department_name,
            "owner_user_id": contribution.owner_user_id,
            "requested_to_user_id": request.requested_to_user_id,
            "requested_to_label": request.requested_to_label,
            "request_channel": request.request_channel,
            "requested_at": _datetime_to_iso(request.requested_at),
            "due_at": _datetime_to_iso(request.due_at or contribution.due_at),
            "sla_target_hours": request.sla_target_hours,
            "sla_max_hours": request.sla_max_hours,
            "proposal_section_id": contribution.proposal_section_id,
        }
    )


def build_contribution_due_date_set_event_payload(
    *,
    request: ContributionRequest,
    contribution: ContributionUnit,
) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_request_id": str(request.id),
            "due_at": _datetime_to_iso(request.due_at or contribution.due_at),
        }
    )


def build_contribution_received_event_payload(
    *,
    request: ContributionRequest,
    contribution: ContributionUnit,
) -> dict[str, Any]:
    due_at = request.due_at or contribution.due_at
    response_received_at = request.response_received_at
    response_time_hours = _duration_hours(request.requested_at, response_received_at)
    lateness_hours = None
    if _as_utc(due_at) is not None and _as_utc(response_received_at) is not None:
        lateness_hours = round(max(0.0, (_as_utc(response_received_at) - _as_utc(due_at)).total_seconds() / 3600), 2)
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_request_id": str(request.id),
            "requested_at": _datetime_to_iso(request.requested_at),
            "received_at": _datetime_to_iso(response_received_at),
            "due_at": _datetime_to_iso(due_at),
            "response_time_hours": response_time_hours,
            "lateness_hours": lateness_hours,
            "within_deadline": lateness_hours is None or lateness_hours <= 0,
            "within_sla_target": response_time_hours is not None and request.sla_target_hours is not None and response_time_hours <= request.sla_target_hours,
            "within_sla_max": response_time_hours is not None and request.sla_max_hours is not None and response_time_hours <= request.sla_max_hours,
            "response_summary": request.response_summary,
        }
    )


def build_review_cycle_started_event_payload(*, review: ReviewCycle, contribution: ContributionUnit) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_review_cycle_id": str(review.id),
            "stage_name": review.stage_name,
            "reviewer_id": review.reviewer_id,
            "started_at": _datetime_to_iso(review.started_at),
        }
    )


def build_contribution_review_completed_event_payload(
    *,
    review: ReviewCycle,
    contribution: ContributionUnit,
) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_review_cycle_id": str(review.id),
            "stage_name": review.stage_name,
            "reviewer_id": review.reviewer_id,
            "started_at": _datetime_to_iso(review.started_at),
            "completed_at": _datetime_to_iso(review.completed_at),
            "cycle_time_hours": _duration_hours(review.started_at, review.completed_at),
            "outcome": review.outcome,
            "notes": review.notes,
        }
    )


def build_rework_requested_event_payload(*, rework: ReworkAction, contribution: ContributionUnit) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_rework_id": str(rework.id),
            "external_review_cycle_id": str(rework.review_cycle_id) if rework.review_cycle_id else None,
            "assigned_to_user_id": rework.assigned_to_user_id,
            "severity": rework.severity,
            "is_blocking": rework.is_blocking,
            "reason": rework.reason,
            "due_at": _datetime_to_iso(rework.due_at),
            "requested_at": _datetime_to_iso(rework.requested_at),
        }
    )


def build_rework_resolved_event_payload(*, rework: ReworkAction, contribution: ContributionUnit) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_contribution_id": str(contribution.id),
            "external_rework_id": str(rework.id),
            "resolved_at": _datetime_to_iso(rework.resolved_at),
            "requested_at": _datetime_to_iso(rework.requested_at),
            "resolution_time_hours": _duration_hours(rework.requested_at, rework.resolved_at),
            "resolution_notes": rework.resolution_notes,
            "severity": rework.severity,
            "is_blocking": rework.is_blocking,
        }
    )


def build_compliance_gate_opened_event_payload(*, gate: ComplianceGate) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_gate_id": str(gate.id),
            "external_contribution_id": str(gate.contribution_unit_id) if gate.contribution_unit_id else None,
            "gate_name": gate.gate_name,
            "owner_user_id": gate.owner_user_id,
            "due_at": _datetime_to_iso(gate.due_at),
        }
    )


def build_compliance_gate_decision_event_payload(*, gate: ComplianceGate) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_gate_id": str(gate.id),
            "external_contribution_id": str(gate.contribution_unit_id) if gate.contribution_unit_id else None,
            "gate_name": gate.gate_name,
            "status": _enum_value(gate.status),
            "evaluated_at": _datetime_to_iso(gate.evaluated_at),
            "decision_notes": gate.decision_notes,
        }
    )


def build_call_scheduled_event_payload(*, call: CallSession) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_call_session_id": str(call.id),
            "title": call.title,
            "scheduled_at": _datetime_to_iso(call.scheduled_at),
        }
    )


def build_call_attendance_recorded_event_payload(*, record: AttendanceRecord, call: CallSession) -> dict[str, Any]:
    return _compact_dict(
        {
            "external_call_session_id": str(call.id),
            "attendance_record_id": str(record.id),
            "user_id": record.user_id,
            "attendee_label": record.attendee_label,
            "attendance_status": _enum_value(record.attendance_status),
            "recorded_at": _datetime_to_iso(record.recorded_at),
            "scheduled_at": _datetime_to_iso(call.scheduled_at),
        }
    )


def apply_delivery_result(event: KpiDomainEvent, result: KpiClientResult) -> KpiDomainEvent:
    """Update a persisted KPI event row with the outbound delivery result."""

    event.delivery_attempts = (event.delivery_attempts or 0) + 1
    event.response_status_code = result.status_code
    event.response_json = result.response_json
    event.updated_at = datetime.now(timezone.utc)

    if result.delivered:
        event.delivery_status = KpiEventDeliveryStatus.DELIVERED
        event.error_message = None
        event.published_at = datetime.now(timezone.utc)
        return event

    event.delivery_status = KpiEventDeliveryStatus.FAILED
    event.error_message = result.error_message
    return event


async def load_tender_for_kpi(db: AsyncSession, tender_id: int) -> Tender | None:
    """Load the tender aggregate needed to build a KPI sync payload."""

    result = await db.execute(
        select(Tender)
        .where(Tender.id == tender_id)
        .options(
            selectinload(Tender.requirements),
            selectinload(Tender.proposals).selectinload(Proposal.sections),
        )
    )
    return result.scalar_one_or_none()


async def publish_tender_sync(
    db: AsyncSession,
    *,
    tender_id: int,
    actor_id: int | None = None,
    source: str = "tw-backend",
    client: KpiReasonEngineClient | None = None,
) -> KpiDomainEvent | None:
    """Persist and deliver the latest tender snapshot to the KPI service."""

    tender = await load_tender_for_kpi(db, tender_id)
    if tender is None:
        logger.warning("kpi.sync.skipped_missing_tender", tender_id=tender_id)
        return None

    payload = build_tender_sync_payload(tender)
    event = KpiDomainEvent(
        tender_id=tender.id,
        actor_id=actor_id,
        event_type="tender_sync",
        source=source,
        external_tender_id=str(tender.id),
        occurred_at=datetime.now(timezone.utc),
        payload_json=payload,
        delivery_status=KpiEventDeliveryStatus.PENDING,
        response_json={},
    )
    db.add(event)
    await db.flush()

    client = client or KpiReasonEngineClient()
    result = await client.sync_tender(payload)
    apply_delivery_result(event, result)
    await db.flush()
    return event


async def publish_domain_event(
    db: AsyncSession,
    *,
    tender_id: int,
    event_type: str,
    payload: dict[str, Any],
    actor_id: int | None = None,
    occurred_at: datetime | None = None,
    source: str = "tw-backend",
    client: KpiReasonEngineClient | None = None,
) -> KpiDomainEvent:
    """Persist and deliver a canonical domain event to the KPI service."""

    occurred_at = _as_utc(occurred_at) or datetime.now(timezone.utc)
    envelope = build_domain_event_payload(
        event_type=event_type,
        occurred_at=occurred_at,
        payload=payload,
        actor_id=actor_id,
        source=source,
    )
    event = KpiDomainEvent(
        tender_id=tender_id,
        actor_id=actor_id,
        event_type=event_type,
        source=source,
        external_tender_id=str(tender_id),
        occurred_at=occurred_at,
        payload_json=envelope,
        delivery_status=KpiEventDeliveryStatus.PENDING,
        response_json={},
    )
    db.add(event)
    await db.flush()

    client = client or KpiReasonEngineClient()
    result = await client.publish_event(str(tender_id), envelope)
    apply_delivery_result(event, result)
    await db.flush()
    return event


async def sync_tender_and_publish_event(
    db: AsyncSession,
    *,
    tender_id: int,
    event_type: str | None = None,
    event_payload: dict[str, Any] | None = None,
    actor_id: int | None = None,
    occurred_at: datetime | None = None,
    source: str = "tw-backend",
    client: KpiReasonEngineClient | None = None,
) -> tuple[KpiDomainEvent | None, KpiDomainEvent | None]:
    """Sync the latest tender snapshot and optionally emit a base domain event."""

    client = client or KpiReasonEngineClient()
    sync_event = await publish_tender_sync(
        db,
        tender_id=tender_id,
        actor_id=actor_id,
        source=source,
        client=client,
    )

    domain_event = None
    if event_type and event_payload is not None:
        domain_event = await publish_domain_event(
            db,
            tender_id=tender_id,
            event_type=event_type,
            payload=event_payload,
            actor_id=actor_id,
            occurred_at=occurred_at,
            source=source,
            client=client,
        )

    return sync_event, domain_event
