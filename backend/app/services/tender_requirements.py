"""Helpers for auto-extracted tender requirements."""

from __future__ import annotations

import re
from typing import Any, Sequence

from app.models import ComplianceStatus, Tender, TenderRequirement


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
