"""Admin KPI API proxy endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.config import settings
from app.db.database import get_db
from app.intelligence.rehearsal_summary import (
    build_rehearsal_summary,
    empty_rehearsal_summary,
)
from app.models import KpiAdminAuditLog, KpiEventDeliveryStatus, Tender
from app.services.kpi_reason_engine import (
    KpiClientResult,
    KpiReasonEngineClient,
    publish_tender_sync,
)

logger = structlog.get_logger(__name__)

router = APIRouter()

_ANALYSIS_METADATA_LIST_FIELDS = {
    "markov_phase_scope",
    "markov_reliable_phase_scope",
    "semantic_priority",
    "canonical_source_types",
    "semantic_kpis",
    "semantic_fallback_kpis",
    "shadow_kpis",
    "forecast_engine_candidates",
    "markov_state_scope",
    "markov_absorbing_states",
    "markov_projected_path",
    "forecast_driver_kpis",
    "scored_kpis",
}
_ANALYSIS_METADATA_INT_DICT_FIELDS = {"markov_source_mix"}
_ANALYSIS_METADATA_FLOAT_DICT_FIELDS = {"forecast_driver_scores"}
_ANALYSIS_METADATA_BOOL_FIELDS = {
    "semantic_official_enabled",
    "shadow_rollout_enabled",
    "markov_rollout_enabled",
    "calibrated_forecast_enabled",
    "shadow_mode_enabled",
    "markov_model_active",
    "markov_full_journey_enabled",
    "reconstructed",
}
_ANALYSIS_METADATA_DEFAULTS: dict[str, Any] = {
    "formula_bundle_version": None,
    "model_bundle_version": None,
    "prompt_bundle_version": None,
    "snapshot_output_schema_version": None,
    "forecast_output_schema_version": None,
    "contract_version": None,
    "health_rule_version": None,
    "score_scale_internal": None,
    "score_scale_external": None,
    "markov_phase_scope": [],
    "markov_reliable_phase_scope": [],
    "semantic_priority": [],
    "canonical_source_types": [],
    "rollout_policy": None,
    "qualitative_engine_kind": None,
    "qualitative_engine_mode": None,
    "semantic_official_enabled": False,
    "semantic_engine_kind": None,
    "semantic_execution_mode": None,
    "semantic_bundle_version": None,
    "semantic_kpis": [],
    "semantic_fallback_kpis": [],
    "semantic_fallback_policy_version": None,
    "shadow_rollout_enabled": False,
    "markov_rollout_enabled": False,
    "calibrated_forecast_enabled": False,
    "shadow_mode_enabled": False,
    "shadow_engine_kind": None,
    "shadow_execution_mode": None,
    "shadow_bundle_version": None,
    "shadow_kpis": [],
    "forecast_engine_active": None,
    "forecast_engine_candidates": [],
    "forecast_signal_type": None,
    "forecast_fallback_reason": None,
    "heuristic_bundle_version": None,
    "markov_model_active": False,
    "markov_model_version": None,
    "markov_state_scope": [],
    "markov_absorbing_states": [],
    "markov_transition_samples": None,
    "markov_dataset_tenders": None,
    "markov_current_state_support": None,
    "markov_source_mix": {},
    "markov_bundle_kind": None,
    "markov_full_journey_enabled": False,
    "markov_coverage_ratio": None,
    "markov_projected_path": [],
    "markov_backtest_version": None,
    "markov_backtest_sample_count": None,
    "markov_backtest_submission_accuracy": None,
    "markov_backtest_calibration_gap": None,
    "forecast_driver_kpis": [],
    "forecast_driver_scores": {},
    "forecast_primary_action_code": None,
    "forecast_primary_action_confidence": None,
    "forecast_decision_bundle_version": None,
    "engine_kind": None,
    "scored_kpis": [],
    "event_count": None,
    "requirements_tracked": None,
    "sections_tracked": None,
    "reconstructed": False,
    "replay_until": None,
    "replay_source_event_type": None,
    "source_job_type": None,
    "history_points": None,
}


def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


def _error_detail(result: KpiClientResult, action: str) -> str:
    return result.error_message or f"KPI reason engine {action} failed."


def _unwrap_action_result(result: KpiClientResult, *, action: str) -> dict[str, Any]:
    if result.delivered:
        payload = dict(result.response_json)
        payload.setdefault("degraded", False)
        payload.setdefault("upstream_status_code", result.status_code)
        return payload

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=_error_detail(result, action),
    )


def _audit_admin_event(
    *,
    action: str,
    current_user: UserResponse,
    tender_id: int | None = None,
    result: KpiClientResult | None = None,
) -> None:
    logger.info(
        "admin_kpi.audit",
        action=action,
        admin_user_id=current_user.id,
        admin_user_email=current_user.email,
        admin_user_role=current_user.role,
        tender_id=tender_id,
        delivered=result.delivered if result is not None else None,
        degraded=(False if result is None else not result.delivered),
        upstream_status_code=None if result is None else result.status_code,
        error_message=None if result is None else result.error_message,
    )


async def _persist_sensitive_admin_audit(
    *,
    db: AsyncSession | Any,
    action: str,
    current_user: UserResponse,
    tender_id: int | None = None,
    result: KpiClientResult | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if not isinstance(db, AsyncSession):
        return
    try:
        db.add(
            KpiAdminAuditLog(
                action=action,
                tender_id=tender_id,
                admin_user_id=current_user.id,
                admin_user_email=current_user.email,
                admin_user_role=current_user.role,
                delivered=None if result is None else result.delivered,
                degraded=(False if result is None else not result.delivered),
                upstream_status_code=None if result is None else result.status_code,
                error_message=None if result is None else result.error_message,
                payload_json=dict(payload or {}),
            )
        )
        await db.flush()
    except Exception:
        logger.exception(
            "admin_kpi.audit_persist_failed",
            action=action,
            tender_id=tender_id,
            admin_user_id=current_user.id,
        )


def _service_status_component(
    result: KpiClientResult, *, action: str, fallback: dict[str, Any]
) -> dict[str, Any]:
    if result.delivered:
        payload = dict(result.response_json)
        payload.setdefault("degraded", False)
        payload.setdefault("upstream_status_code", result.status_code)
        return payload
    payload = dict(fallback)
    payload["degraded"] = True
    payload["degraded_reason"] = _error_detail(result, action)
    payload["upstream_status_code"] = result.status_code
    return payload


def _clone_default_analysis_metadata() -> dict[str, Any]:
    cloned: dict[str, Any] = {}
    for key, value in _ANALYSIS_METADATA_DEFAULTS.items():
        if isinstance(value, list):
            cloned[key] = list(value)
        elif isinstance(value, dict):
            cloned[key] = dict(value)
        else:
            cloned[key] = value
    return cloned


def _normalize_analysis_metadata(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _clone_default_analysis_metadata()
    source = payload if isinstance(payload, dict) else {}
    for key, default in normalized.items():
        if key in _ANALYSIS_METADATA_LIST_FIELDS:
            value = source.get(key)
            normalized[key] = (
                [str(item) for item in value] if isinstance(value, list) else list(default)
            )
            continue
        if key in _ANALYSIS_METADATA_INT_DICT_FIELDS:
            value = source.get(key)
            if isinstance(value, dict):
                normalized[key] = {
                    str(item_key): int(item_value) for item_key, item_value in value.items()
                }
            else:
                normalized[key] = dict(default)
            continue
        if key in _ANALYSIS_METADATA_FLOAT_DICT_FIELDS:
            value = source.get(key)
            if isinstance(value, dict):
                normalized[key] = {
                    str(item_key): float(item_value) for item_key, item_value in value.items()
                }
            else:
                normalized[key] = dict(default)
            continue
        if key in _ANALYSIS_METADATA_BOOL_FIELDS:
            normalized[key] = bool(source.get(key, default))
            continue
        normalized[key] = source.get(key, default)
    return normalized


def _normalize_shadow_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "enabled": bool(payload.get("enabled", True)),
        "status": payload.get("status") or "shadow",
        "engine_kind": payload.get("engine_kind"),
        "execution_mode": payload.get("execution_mode"),
        "shadow_score": payload.get("shadow_score"),
        "proxy_score": payload.get("proxy_score"),
        "delta_vs_proxy": payload.get("delta_vs_proxy"),
        "health": payload.get("health") or "unknown",
        "confidence": payload.get("confidence"),
        "source_type": payload.get("source_type") or "unknown",
        "evidences": list(payload.get("evidences") or []),
        "criticalities": list(payload.get("criticalities") or []),
        "recommendations": list(payload.get("recommendations") or []),
        "formula_version": payload.get("formula_version"),
        "model_version": payload.get("model_version"),
        "prompt_version": payload.get("prompt_version"),
        "coverage_gaps": list(payload.get("coverage_gaps") or []),
        "risk_items": list(payload.get("risk_items") or []),
    }


def _normalize_semantic_coverage_gap(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_requirement_id": payload.get("external_requirement_id") or "unknown",
        "reference": payload.get("reference"),
        "summary": payload.get("summary"),
        "priority": payload.get("priority"),
        "status": payload.get("status"),
        "mapped_section_id": payload.get("mapped_section_id"),
    }


def _normalize_semantic_risk_item(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": payload.get("code") or "unknown",
        "severity": payload.get("severity") or "unknown",
        "summary": payload.get("summary") or "Unknown semantic risk.",
        "related_requirement_id": payload.get("related_requirement_id"),
        "evidence": payload.get("evidence"),
    }


def _normalize_semantic_dimension_item(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": payload.get("code") or "unknown",
        "severity": payload.get("severity") or "unknown",
        "summary": payload.get("summary") or "Unknown semantic dimension.",
        "evidence": payload.get("evidence"),
    }


def _normalize_semantic_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "enabled": bool(payload.get("enabled", True)),
        "status": payload.get("status")
        or ("fallback" if payload.get("fallback_reason") else "official"),
        "engine_kind": payload.get("engine_kind"),
        "execution_mode": payload.get("execution_mode"),
        "semantic_score": payload.get("semantic_score"),
        "proxy_score": payload.get("proxy_score"),
        "delta_vs_proxy": payload.get("delta_vs_proxy"),
        "health": payload.get("health") or "unknown",
        "confidence": payload.get("confidence"),
        "source_type": payload.get("source_type") or "unknown",
        "evidences": list(payload.get("evidences") or []),
        "criticalities": list(payload.get("criticalities") or []),
        "recommendations": list(payload.get("recommendations") or []),
        "formula_version": payload.get("formula_version"),
        "model_version": payload.get("model_version"),
        "prompt_version": payload.get("prompt_version"),
        "fallback_reason": payload.get("fallback_reason"),
        "coverage_gaps": [
            _normalize_semantic_coverage_gap(item)
            for item in payload.get("coverage_gaps") or []
            if isinstance(item, dict)
        ],
        "risk_items": [
            _normalize_semantic_risk_item(item)
            for item in payload.get("risk_items") or []
            if isinstance(item, dict)
        ],
        "dimension_items": [
            _normalize_semantic_dimension_item(item)
            for item in payload.get("dimension_items") or []
            if isinstance(item, dict)
        ],
    }


def _normalize_kpi_score(payload: dict[str, Any]) -> dict[str, Any]:
    evidence_items = list(payload.get("evidences") or payload.get("evidence") or [])
    recommendation_items = list(payload.get("recommendations") or [])
    if not recommendation_items and payload.get("recommendation"):
        recommendation_items = [payload["recommendation"]]
    source_type = payload.get("source_type") or payload.get("provenance") or "unknown"
    return {
        "kpi_code": str(payload.get("kpi_code") or "unknown"),
        "score": payload.get("score", payload.get("value")),
        "value": payload.get("value", payload.get("score")),
        "label": payload.get("label"),
        "health": payload.get("health") or "unknown",
        "severity": payload.get("severity") or "unknown",
        "source_type": source_type,
        "provenance": source_type,
        "confidence": payload.get("confidence"),
        "evidences": evidence_items,
        "evidence": evidence_items,
        "criticalities": list(payload.get("criticalities") or []),
        "recommendations": recommendation_items,
        "recommendation": payload.get("recommendation")
        or (recommendation_items[0] if recommendation_items else None),
        "formula_version": payload.get("formula_version"),
        "model_version": payload.get("model_version"),
        "prompt_version": payload.get("prompt_version"),
        "semantic": _normalize_semantic_payload(payload.get("semantic")),
        "shadow": _normalize_shadow_payload(payload.get("shadow")),
    }


def _normalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["kpis"] = [
        _normalize_kpi_score(item) for item in payload.get("kpis") or [] if isinstance(item, dict)
    ]
    normalized["analysis_metadata"] = _normalize_analysis_metadata(payload.get("analysis_metadata"))
    normalized.setdefault("notes", [])
    return normalized


def _normalize_diagnostics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["analysis_metadata"] = _normalize_analysis_metadata(payload.get("analysis_metadata"))
    normalized.setdefault("findings", [])
    return normalized


def _normalize_transitions_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["items"] = [
        {
            "from_state": item.get("from_state"),
            "to_state": item.get("to_state"),
            "occurred_at": item.get("occurred_at"),
            "cause": item.get("cause"),
            "confidence": item.get("confidence"),
            "source_event_type": item.get("source_event_type"),
            "source_type": item.get("source_type") or "unknown",
            "related_entity_id": item.get("related_entity_id"),
        }
        for item in payload.get("items") or []
        if isinstance(item, dict)
    ]
    normalized["requirement_items"] = [
        item for item in payload.get("requirement_items") or [] if isinstance(item, dict)
    ]
    normalized["history_items"] = [
        {
            "snapshot_id": item.get("snapshot_id"),
            "generated_at": item.get("generated_at"),
            "analytical_phase": item.get("analytical_phase"),
            "health": item.get("health") or "unknown",
            "summary": item.get("summary"),
            "reconstructed": bool(item.get("reconstructed", False)),
            "replay_until": item.get("replay_until"),
            "source_type": item.get("source_type") or "unknown",
            "source_job_type": item.get("source_job_type"),
            "replay_source_event_type": item.get("replay_source_event_type"),
        }
        for item in payload.get("history_items") or []
        if isinstance(item, dict)
    ]
    return normalized


def _normalize_forecast_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["scenarios"] = [
        {
            "name": item.get("name") or "unknown",
            "probability": item.get("probability"),
            "description": item.get("description"),
            "confidence": item.get("confidence"),
            "drivers": list(item.get("drivers") or []),
            "recommended_action": item.get("recommended_action"),
        }
        for item in payload.get("scenarios") or []
        if isinstance(item, dict)
    ]
    normalized["next_best_actions"] = [
        {
            "code": item.get("code") or "unknown",
            "title": item.get("title") or "Untitled action",
            "priority": item.get("priority") or "now",
            "rationale": item.get("rationale") or "No rationale available.",
            "expected_impact": item.get("expected_impact"),
            "confidence": item.get("confidence"),
            "drivers": list(item.get("drivers") or []),
        }
        for item in payload.get("next_best_actions") or []
        if isinstance(item, dict)
    ]
    normalized["analysis_metadata"] = _normalize_analysis_metadata(payload.get("analysis_metadata"))
    return normalized


def _normalize_portfolio_intelligence_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["phase_hotspots"] = [
        {
            "phase": item.get("phase") or "analysis_pending",
            "count": int(item.get("count") or 0),
            "summary": item.get("summary") or "No summary available.",
        }
        for item in payload.get("phase_hotspots") or []
        if isinstance(item, dict)
    ]
    normalized["risk_hotspots"] = [
        {
            "code": item.get("code") or "unknown",
            "count": int(item.get("count") or 0),
            "severity": item.get("severity") or "unknown",
            "summary": item.get("summary") or "No summary available.",
        }
        for item in payload.get("risk_hotspots") or []
        if isinstance(item, dict)
    ]
    normalized["outcome_trends"] = {
        str(item_key): int(item_value)
        for item_key, item_value in (payload.get("outcome_trends") or {}).items()
    }
    normalized["watchlist"] = [
        {
            "external_tender_id": str(item.get("external_tender_id") or "unknown"),
            "title": item.get("title") or "Untitled tender",
            "analytical_phase": item.get("analytical_phase"),
            "health": item.get("health") or "unknown",
            "summary": item.get("summary") or "No summary available.",
        }
        for item in payload.get("watchlist") or []
        if isinstance(item, dict)
    ]
    normalized["notes"] = list(payload.get("notes") or [])
    return normalized


def _overview_fallback(detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "generated_at": None,
        "portfolio_health": "unknown",
        "total_tenders": 0,
        "tenders_by_health": {},
        "analytical_phases": {},
        "critical_tenders": [],
        "notes": [detail],
    }


def _bottlenecks_fallback(detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "generated_at": None,
        "items": [],
        "notes": [detail],
    }


def _snapshot_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "analytical_phase": None,
        "health": "unknown",
        "generated_at": None,
        "kpis": [],
        "notes": [detail],
        "analysis_metadata": _clone_default_analysis_metadata(),
    }


def _diagnostics_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": "KPI service temporarily unavailable.",
        "findings": [detail],
        "analysis_metadata": _clone_default_analysis_metadata(),
    }


def _transitions_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": detail,
        "items": [],
        "requirement_items": [],
        "history_items": [],
    }


def _forecast_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": detail,
        "overall_confidence": 0.0,
        "scenarios": [
            {
                "name": "service_unavailable",
                "probability": None,
                "description": detail,
                "confidence": 0.0,
                "drivers": [detail],
                "recommended_action": "Retry when the KPI service becomes available.",
            }
        ],
        "next_best_actions": [
            {
                "code": "restore_kpi_service",
                "title": "Restore KPI service connectivity",
                "priority": "now",
                "rationale": detail,
                "expected_impact": "Unlock forecast and decision-support again.",
                "confidence": 0.0,
                "drivers": [detail],
            }
        ],
        "analysis_metadata": _clone_default_analysis_metadata(),
    }


def _portfolio_intelligence_fallback(detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "generated_at": None,
        "phase_hotspots": [],
        "risk_hotspots": [],
        "outcome_trends": {},
        "watchlist": [],
        "notes": [detail],
    }


def _analysis_job_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "external_tender_id": str(tender_id),
        "job_id": None,
        "job_type": None,
        "job_status": "degraded",
        "requested_by": None,
        "priority": None,
        "reason": None,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": datetime.now(UTC).isoformat(),
        "latest_snapshot_generated_at": None,
        "error_message": detail,
    }


def _query_or_fallback(
    result: KpiClientResult, *, action: str, fallback: dict[str, Any]
) -> dict[str, Any]:
    if result.delivered:
        payload = dict(result.response_json)
        payload.setdefault("degraded", False)
        payload.setdefault("upstream_status_code", result.status_code)
        return payload
    fallback.setdefault("error_message", _error_detail(result, action))
    fallback.setdefault("degraded", True)
    fallback.setdefault("degraded_reason", _error_detail(result, action))
    fallback.setdefault("upstream_status_code", result.status_code)
    return fallback


def _sync_result_metadata(result: KpiClientResult) -> dict[str, Any]:
    return {
        "delivered": result.delivered,
        "upstream_status_code": result.status_code,
        "error_message": result.error_message,
    }


async def _sync_tender_before_analysis_job(
    *,
    tender_id: int,
    current_user: UserResponse,
    db: AsyncSession,
    client: KpiReasonEngineClient,
) -> KpiClientResult:
    sync_event = await publish_tender_sync(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        source="tw-backend",
        client=client,
    )
    if sync_event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender {tender_id} not found.",
        )

    delivery_status = getattr(sync_event.delivery_status, "value", sync_event.delivery_status)
    return KpiClientResult(
        delivered=delivery_status == KpiEventDeliveryStatus.DELIVERED.value,
        status_code=sync_event.response_status_code,
        response_json=dict(sync_event.response_json or {}),
        error_message=sync_event.error_message,
    )


async def _load_portfolio_tender_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(Tender.id).order_by(Tender.id.asc()))
    return list(result.scalars().all())


@router.get("/portfolio/overview", response_model=dict[str, Any])
async def get_kpi_portfolio_overview(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_overview()
    _audit_admin_event(action="portfolio_overview_query", current_user=current_user, result=result)
    return _query_or_fallback(
        result,
        action="portfolio overview query",
        fallback=_overview_fallback(_error_detail(result, "portfolio overview query")),
    )


@router.get("/portfolio/bottlenecks", response_model=dict[str, Any])
async def get_kpi_portfolio_bottlenecks(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_bottlenecks()
    _audit_admin_event(
        action="portfolio_bottlenecks_query", current_user=current_user, result=result
    )
    return _query_or_fallback(
        result,
        action="portfolio bottlenecks query",
        fallback=_bottlenecks_fallback(_error_detail(result, "portfolio bottlenecks query")),
    )


@router.get("/portfolio/intelligence", response_model=dict[str, Any])
async def get_kpi_portfolio_intelligence(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_intelligence()
    _audit_admin_event(
        action="portfolio_intelligence_query", current_user=current_user, result=result
    )
    return _normalize_portfolio_intelligence_payload(
        _query_or_fallback(
            result,
            action="portfolio intelligence query",
            fallback=_portfolio_intelligence_fallback(
                _error_detail(result, "portfolio intelligence query")
            ),
        )
    )


@router.get("/service/status", response_model=dict[str, Any])
async def get_kpi_service_status(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    health_result = await client.get_service_health()
    readiness_result = await client.get_service_readiness()
    manifest_result = await client.get_version_manifest()
    primary_result = (
        health_result
        if health_result.delivered
        else readiness_result
        if readiness_result.delivered
        else manifest_result
    )
    _audit_admin_event(
        action="service_status_query", current_user=current_user, result=primary_result
    )

    health_payload = _service_status_component(
        health_result,
        action="service health query",
        fallback={
            "status": "healthy",
            "service": "tw-kpi-reason-engine",
            "version": None,
            "ready": False,
        },
    )
    readiness_payload = _service_status_component(
        readiness_result,
        action="service readiness query",
        fallback={
            "status": "degraded",
            "service": "tw-kpi-reason-engine",
            "version": None,
            "ready": False,
            "warnings": [],
            "dependencies": [],
        },
    )
    manifest_payload = _service_status_component(
        manifest_result,
        action="service version manifest query",
        fallback={
            "status": "available",
            "service": "tw-kpi-reason-engine",
            "version": None,
            "entries": [],
        },
    )
    degraded = not (
        health_result.delivered and readiness_result.delivered and manifest_result.delivered
    )
    return {
        "status": "degraded" if degraded else "ready",
        "degraded": degraded,
        "generated_at": datetime.now(UTC).isoformat(),
        "health": health_payload,
        "readiness": readiness_payload,
        "version_manifest": manifest_payload,
        "notes": [
            "One or more KPI service runtime endpoints are degraded; inspect upstream status codes and degraded reasons."
            if degraded
            else "KPI service runtime endpoints are healthy and version-governed."
        ],
    }


@router.post("/portfolio/resync", response_model=dict[str, Any])
async def resync_kpi_portfolio(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    tender_ids = await _load_portfolio_tender_ids(db)
    items: list[dict[str, Any]] = []
    synced_tenders = 0
    failed_tenders = 0

    for tender_id in tender_ids:
        try:
            sync_result = await _sync_tender_before_analysis_job(
                tender_id=tender_id,
                current_user=current_user,
                db=db,
                client=client,
            )
        except HTTPException as exc:
            sync_result = KpiClientResult(
                delivered=False,
                status_code=exc.status_code,
                response_json={},
                error_message=str(exc.detail),
            )
        except Exception as exc:
            sync_result = KpiClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message=str(exc),
            )

        _audit_admin_event(
            action="portfolio_tender_resync",
            current_user=current_user,
            tender_id=tender_id,
            result=sync_result,
        )
        items.append({"tender_id": tender_id, **_sync_result_metadata(sync_result)})
        if sync_result.delivered:
            synced_tenders += 1
        else:
            failed_tenders += 1

    response_payload = {
        "status": "completed",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_tenders": len(tender_ids),
        "synced_tenders": synced_tenders,
        "failed_tenders": failed_tenders,
        "items": items,
        "notes": [
            "Portfolio resync completed successfully."
            if failed_tenders == 0
            else "Portfolio resync completed with partial failures.",
        ],
    }
    await _persist_sensitive_admin_audit(
        db=db,
        action="portfolio_resync",
        current_user=current_user,
        result=KpiClientResult(
            delivered=(failed_tenders == 0),
            status_code=200,
            response_json={},
            error_message=(
                None if failed_tenders == 0 else "Portfolio resync completed with partial failures."
            ),
        ),
        payload=response_payload,
    )
    return response_payload


@router.get("/tenders/{tender_id}/snapshot", response_model=dict[str, Any])
async def get_kpi_tender_snapshot(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_snapshot(str(tender_id))
    _audit_admin_event(
        action="tender_snapshot_query",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    return _normalize_snapshot_payload(
        _query_or_fallback(
            result,
            action="tender snapshot query",
            fallback=_snapshot_fallback(tender_id, _error_detail(result, "tender snapshot query")),
        )
    )


@router.get("/tenders/{tender_id}/diagnostics", response_model=dict[str, Any])
async def get_kpi_tender_diagnostics(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_diagnostics(str(tender_id))
    _audit_admin_event(
        action="tender_diagnostics_query",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    return _normalize_diagnostics_payload(
        _query_or_fallback(
            result,
            action="tender diagnostics query",
            fallback=_diagnostics_fallback(
                tender_id, _error_detail(result, "tender diagnostics query")
            ),
        )
    )


@router.get("/tenders/{tender_id}/transitions", response_model=dict[str, Any])
async def get_kpi_tender_transitions(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_transitions(str(tender_id))
    _audit_admin_event(
        action="tender_transitions_query",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    return _normalize_transitions_payload(
        _query_or_fallback(
            result,
            action="tender transitions query",
            fallback=_transitions_fallback(
                tender_id, _error_detail(result, "tender transitions query")
            ),
        )
    )


@router.get("/tenders/{tender_id}/forecast", response_model=dict[str, Any])
async def get_kpi_tender_forecast(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_forecast(str(tender_id))
    _audit_admin_event(
        action="tender_forecast_query",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    normalized = _normalize_forecast_payload(
        _query_or_fallback(
            result,
            action="tender forecast query",
            fallback=_forecast_fallback(tender_id, _error_detail(result, "tender forecast query")),
        )
    )

    if settings.rehearsal_summary_enabled:
        engine_summary = normalized.get("rehearsal_summary")
        summary: dict[str, Any] | None = (
            engine_summary if isinstance(engine_summary, dict) and engine_summary else None
        )
        if summary is None:
            try:
                summary = await build_rehearsal_summary(db, tender_id=tender_id)
            except Exception:
                logger.exception("rehearsal_summary_enrichment_failed", tender_id=tender_id)
                summary = None

        if summary is None:
            summary = empty_rehearsal_summary()
            summary["tender_id"] = tender_id
        normalized["rehearsal_summary"] = summary
    return normalized


@router.post(
    "/tenders/{tender_id}/recompute",
    response_model=dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
)
async def recompute_kpi_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    sync_result = await _sync_tender_before_analysis_job(
        tender_id=tender_id,
        current_user=current_user,
        db=db,
        client=client,
    )
    _audit_admin_event(
        action="tender_resync_before_recompute",
        current_user=current_user,
        tender_id=tender_id,
        result=sync_result,
    )
    if not sync_result.delivered:
        await _persist_sensitive_admin_audit(
            db=db,
            action="tender_recompute_request",
            current_user=current_user,
            tender_id=tender_id,
            result=sync_result,
            payload={"stage": "tender_sync"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(sync_result, "tender resync before recompute"),
        )

    result = await client.request_analysis_job(
        str(tender_id),
        {
            "job_type": "full_recompute",
            "requested_by": str(current_user.id),
            "priority": "high",
            "reason": "Manual admin recompute",
            "metadata": {
                "source": "admin-ui",
                "requested_by_name": current_user.name,
                "resync_before_job": True,
            },
        },
    )
    _audit_admin_event(
        action="tender_recompute_request",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    payload = _unwrap_action_result(result, action="tender recompute request")
    payload.setdefault("tender_sync", _sync_result_metadata(sync_result))
    await _persist_sensitive_admin_audit(
        db=db,
        action="tender_recompute_request",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
        payload=payload,
    )
    return payload


@router.post(
    "/tenders/{tender_id}/history/backfill",
    response_model=dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
)
async def backfill_kpi_tender_history(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    sync_result = await _sync_tender_before_analysis_job(
        tender_id=tender_id,
        current_user=current_user,
        db=db,
        client=client,
    )
    _audit_admin_event(
        action="tender_resync_before_history_backfill",
        current_user=current_user,
        tender_id=tender_id,
        result=sync_result,
    )
    if not sync_result.delivered:
        await _persist_sensitive_admin_audit(
            db=db,
            action="tender_history_backfill_request",
            current_user=current_user,
            tender_id=tender_id,
            result=sync_result,
            payload={"stage": "tender_sync"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(sync_result, "tender resync before history backfill"),
        )

    result = await client.request_analysis_job(
        str(tender_id),
        {
            "job_type": "history_backfill",
            "requested_by": str(current_user.id),
            "priority": "high",
            "reason": "Manual admin history backfill",
            "metadata": {
                "source": "admin-ui",
                "requested_by_name": current_user.name,
                "resync_before_job": True,
            },
        },
    )
    _audit_admin_event(
        action="tender_history_backfill_request",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    payload = _unwrap_action_result(result, action="tender history backfill request")
    payload.setdefault("tender_sync", _sync_result_metadata(sync_result))
    await _persist_sensitive_admin_audit(
        db=db,
        action="tender_history_backfill_request",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
        payload=payload,
    )
    return payload


@router.get("/tenders/{tender_id}/analysis-jobs/latest", response_model=dict[str, Any])
async def get_kpi_latest_analysis_job(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_latest_analysis_job(str(tender_id))
    _audit_admin_event(
        action="latest_analysis_job_query",
        current_user=current_user,
        tender_id=tender_id,
        result=result,
    )
    return _query_or_fallback(
        result,
        action="latest analysis job query",
        fallback=_analysis_job_fallback(
            tender_id, _error_detail(result, "latest analysis job query")
        ),
    )
