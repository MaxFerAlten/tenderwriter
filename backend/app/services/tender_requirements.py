"""Helpers for auto-extracted tender requirements."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from app.intelligence.lifecycle_projector import project_requirement_event
from app.intelligence.ontology import default_ontology_service
from app.models import ComplianceStatus, Tender, TenderRequirement

logger = structlog.get_logger()


def normalize_requirement_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _normalize_requirement_identity_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    without_accents = "".join(
        ch for ch in unicodedata.normalize("NFKD", collapsed) if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", without_accents).strip(" .;:")


def compute_requirement_identity_hash(value: str, *, tender_id: int | str) -> str:
    """Stable content identity for graph upserts across re-ingestion runs."""

    normalized = _normalize_requirement_identity_text(value)
    return hashlib.sha256(f"{tender_id}::{normalized}".encode()).hexdigest()[:16]


def apply_extracted_requirement_candidates(
    tender: Tender,
    candidates: Sequence[dict[str, Any]],
) -> list[TenderRequirement]:
    existing = {
        normalize_requirement_text(requirement.requirement_text): requirement
        for requirement in list(tender.requirements or [])
        if requirement.requirement_text
    }
    created: list[TenderRequirement] = []

    for candidate in candidates:
        summary = re.sub(r"\s+", " ", str(candidate.get("summary") or "").strip())
        if len(summary) < 15:
            continue

        normalized = normalize_requirement_text(summary)
        if not normalized or normalized in existing:
            continue

        reference = (
            candidate.get("reference")
            or candidate.get("section")
            or candidate.get("source_section")
        )
        category = candidate.get("category") or reference
        priority = str(candidate.get("priority") or "medium").strip().casefold()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"

        requirement = TenderRequirement(
            requirement_text=summary,
            category=str(category) if category else None,
            priority=priority,
            compliance_status=ComplianceStatus.NOT_ADDRESSED,
        )
        tender.requirements.append(requirement)
        existing[normalized] = requirement
        created.append(requirement)

    return created


async def sync_tender_requirements_to_graph(
    rag_engine: Any,
    tender: Tender,
    requirements: Sequence[TenderRequirement] | None = None,
) -> int:
    """Mirror SQL tender requirements into Neo4j Requirement nodes."""
    tender_id = getattr(tender, "id", None)
    if not tender_id:
        return 0

    if not rag_engine:
        return 0

    try:
        await rag_engine.ensure_initialized()
    except Exception as exc:
        logger.warning(
            "RAG engine unavailable while syncing requirements to graph",
            tender_id=tender_id,
            error=str(exc),
        )
        return 0

    graph = getattr(rag_engine, "graph_retriever", None)
    if not graph:
        logger.warning(
            "Graph retriever unavailable while syncing requirements",
            tender_id=tender_id,
        )
        return 0

    tender_payload = {
        "id": str(tender_id),
        "title": str(getattr(tender, "title", "") or f"Tender {tender_id}"),
        "status": getattr(
            getattr(tender, "status", None),
            "value",
            getattr(tender, "status", None),
        ),
        "client": getattr(tender, "client", None),
        "category": getattr(tender, "category", None),
        "deadline": getattr(getattr(tender, "deadline", None), "isoformat", lambda: None)(),
    }

    try:
        await graph.upsert_tender(tender_payload)
    except Exception as exc:
        logger.warning(
            "Failed to upsert tender node in Neo4j",
            tender_id=tender_id,
            error=str(exc),
        )
        return 0

    requirements = list(
        requirements
        if requirements is not None
        else list(getattr(tender, "requirements", []) or [])
    )
    synced = 0
    for requirement in requirements:
        requirement_id = getattr(requirement, "id", None)
        requirement_text = str(getattr(requirement, "requirement_text", "") or "").strip()
        if not requirement_id or not requirement_text:
            continue

        ontology = default_ontology_service().tag_text(
            requirement_text,
            category=str(getattr(requirement, "category", None) or "") or None,
            priority=str(getattr(requirement, "priority", None) or "") or None,
        )
        ontology_payload = ontology.model_dump(mode="json")

        try:
            await graph.add_requirement(
                {
                    "id": f"tender-{tender_id}-requirement-{requirement_id}",
                    "identity_hash": compute_requirement_identity_hash(
                        requirement_text,
                        tender_id=tender_id,
                    ),
                    "text": requirement_text,
                    "category": str(getattr(requirement, "category", None) or "general"),
                    "priority": str(getattr(requirement, "priority", None) or "medium"),
                    **ontology_payload,
                },
                tender_id=str(tender_id),
                tender=tender_payload,
            )
            synced += 1
        except Exception as exc:
            logger.warning(
                "Failed to sync requirement to Neo4j",
                tender_id=tender_id,
                requirement_id=requirement_id,
                error=str(exc),
            )
            continue

        await project_requirement_event(
            rag_engine=rag_engine,
            tender_id=tender_id,
            requirement_id=requirement_id,
            event_type="requirements_extracted",
            occurred_at=datetime.now(UTC),
            external_event_id=f"extract-t{tender_id}-r{requirement_id}",
            payload={"category": str(getattr(requirement, "category", None) or "general")},
        )

    logger.info(
        "Tender requirements synced to graph",
        tender_id=tender_id,
        synced=synced,
    )
    return synced
