"""Helpers for auto-extracted tender requirements."""

from __future__ import annotations

import re
from typing import Any, Sequence

import structlog

from app.models import ComplianceStatus, Tender, TenderRequirement

logger = structlog.get_logger()


def normalize_requirement_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


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

        reference = candidate.get("reference") or candidate.get("section") or candidate.get("source_section")
        priority = str(candidate.get("priority") or "medium").strip().casefold()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"

        requirement = TenderRequirement(
            requirement_text=summary,
            category=str(reference) if reference else None,
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
        logger.warning("Graph retriever unavailable while syncing requirements", tender_id=tender_id)
        return 0

    tender_payload = {
        "id": str(tender_id),
        "title": str(getattr(tender, "title", "") or f"Tender {tender_id}"),
        "status": getattr(getattr(tender, "status", None), "value", getattr(tender, "status", None)),
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

    requirements = list(requirements if requirements is not None else list(getattr(tender, "requirements", []) or []))
    synced = 0
    for requirement in requirements:
        requirement_id = getattr(requirement, "id", None)
        requirement_text = str(getattr(requirement, "requirement_text", "") or "").strip()
        if not requirement_id or not requirement_text:
            continue

        try:
            await graph.add_requirement(
                {
                    "id": f"tender-{tender_id}-requirement-{requirement_id}",
                    "text": requirement_text,
                    "category": str(getattr(requirement, "category", None) or "general"),
                    "priority": str(getattr(requirement, "priority", None) or "medium"),
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

    logger.info(
        "Tender requirements synced to graph",
        tender_id=tender_id,
        synced=synced,
    )
    return synced
