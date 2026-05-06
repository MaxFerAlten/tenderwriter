"""Helpers for document ingestion stage observability."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

INGESTION_STAGE_ORDER = (
    "download",
    "parse",
    "requirement_extraction",
    "chunking",
    "index_qdrant",
    "sync_neo4j",
    "compliance",
    "completed",
)

INGESTION_STAGE_CONFIG: dict[str, dict[str, float | str]] = {
    "download": {
        "label": "Download file",
        "start_progress": 5.0,
        "end_progress": 15.0,
    },
    "parse": {
        "label": "Parse document",
        "start_progress": 20.0,
        "end_progress": 30.0,
    },
    "requirement_extraction": {
        "label": "Requirement extraction",
        "start_progress": 35.0,
        "end_progress": 45.0,
    },
    "chunking": {
        "label": "Chunking",
        "start_progress": 50.0,
        "end_progress": 65.0,
    },
    "index_qdrant": {
        "label": "Index Qdrant",
        "start_progress": 70.0,
        "end_progress": 80.0,
    },
    "sync_neo4j": {
        "label": "Sync Neo4j",
        "start_progress": 85.0,
        "end_progress": 92.0,
    },
    "compliance": {
        "label": "Compliance sync",
        "start_progress": 93.0,
        "end_progress": 97.0,
    },
    "completed": {
        "label": "Completed",
        "start_progress": 100.0,
        "end_progress": 100.0,
    },
}


def _timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, Mapping):
        payload: dict[str, Any] = {}
        for key, item in value.items():
            safe_item = _json_safe(item)
            if safe_item is not None:
                payload[str(key)] = safe_item
        return payload
    if isinstance(value, (list, tuple, set)):
        payload = []
        for item in value:
            safe_item = _json_safe(item)
            if safe_item is not None:
                payload.append(safe_item)
        return payload
    return str(value)


def get_stage_progress(stage: str, status: str) -> float:
    config = INGESTION_STAGE_CONFIG.get(stage) or {}
    start_progress = float(config.get("start_progress") or 0.0)
    end_progress = float(config.get("end_progress") or start_progress)
    if status == "started":
        return start_progress
    if status == "failed":
        return start_progress
    return end_progress


def extract_ingestion_observability(metadata_json: Any) -> dict[str, Any]:
    if not isinstance(metadata_json, Mapping):
        return {}
    value = metadata_json.get("ingestion_observability")
    return dict(value) if isinstance(value, Mapping) else {}


def update_ingestion_observability(
    metadata_json: Any,
    *,
    stage: str,
    status: str,
    detail: str | None = None,
    stats: Mapping[str, Any] | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    base_metadata = dict(metadata_json) if isinstance(metadata_json, Mapping) else {}
    observability = extract_ingestion_observability(base_metadata)
    raw_stages = observability.get("stages")
    stages = (
        {
            str(name): dict(payload)
            for name, payload in raw_stages.items()
            if isinstance(payload, Mapping)
        }
        if isinstance(raw_stages, Mapping)
        else {}
    )

    config = INGESTION_STAGE_CONFIG.get(stage) or {}
    timestamp = _timestamp(now)
    stage_state = dict(stages.get(stage) or {})

    stage_state["label"] = str(config.get("label") or stage.replace("_", " ").title())
    stage_state["order"] = (
        INGESTION_STAGE_ORDER.index(stage)
        if stage in INGESTION_STAGE_ORDER
        else len(INGESTION_STAGE_ORDER)
    )
    stage_state["status"] = status
    stage_state["updated_at"] = timestamp

    if status == "started":
        stage_state["started_at"] = stage_state.get("started_at") or timestamp
        stage_state.pop("completed_at", None)
        stage_state.pop("failed_at", None)
        stage_state.pop("error_message", None)
    elif status in {"completed", "skipped"}:
        stage_state["started_at"] = stage_state.get("started_at") or timestamp
        stage_state["completed_at"] = timestamp
        stage_state.pop("failed_at", None)
        stage_state.pop("error_message", None)
    elif status == "failed":
        stage_state["started_at"] = stage_state.get("started_at") or timestamp
        stage_state["failed_at"] = timestamp

    if detail is not None:
        stage_state["detail"] = str(detail)

    safe_stats = _json_safe(dict(stats)) if stats else {}
    if isinstance(safe_stats, dict) and safe_stats:
        stage_state["stats"] = safe_stats

    if error_message is not None:
        stage_state["error_message"] = str(error_message)

    stages[stage] = stage_state
    progress = get_stage_progress(stage, status)

    observability.update(
        {
            "version": "ingestion_observability_v1",
            "started_at": observability.get("started_at") or timestamp,
            "updated_at": timestamp,
            "current_stage": stage,
            "current_stage_label": stage_state["label"],
            "current_stage_status": status,
            "current_stage_detail": stage_state.get("detail"),
            "progress": progress,
            "completed_stages": [
                name
                for name in INGESTION_STAGE_ORDER
                if (stages.get(name) or {}).get("status") in {"completed", "skipped"}
            ],
            "stages": stages,
        }
    )

    if status == "failed":
        observability["failed_stage"] = stage
        observability["failure"] = {
            "stage": stage,
            "message": str(error_message or ""),
            "at": timestamp,
        }
    elif stage == "completed" and status == "completed":
        observability["completed_at"] = timestamp
        observability.pop("failed_stage", None)
        observability.pop("failure", None)

    base_metadata["ingestion_observability"] = observability
    return base_metadata
