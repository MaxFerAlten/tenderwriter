"""Deterministic rollout controls for requirement extraction upgrades."""

from __future__ import annotations

import hashlib
from typing import Any

from app.config import settings as app_settings


_ROLLOUT_SALT = "requirement_extraction_llm_v2"


def parse_tender_id_set(value: Any) -> set[int]:
    """Parse comma-separated tender ids into a normalized positive-id set."""

    if value is None:
        return set()
    raw_values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    tender_ids: set[int] = set()
    for raw_value in raw_values:
        text = str(raw_value).strip()
        if not text:
            continue
        tender_id = int(text)
        if tender_id <= 0:
            raise ValueError("tender rollout ids must be positive integers")
        tender_ids.add(tender_id)
    return tender_ids


def requirement_rollout_bucket(tender_id: int, *, salt: str = _ROLLOUT_SALT) -> int:
    """Return a stable 0-99 rollout bucket for a tender id."""

    normalized_tender_id = int(tender_id)
    if normalized_tender_id <= 0:
        raise ValueError("tender_id must be a positive integer")
    digest = hashlib.sha256(f"{salt}:{normalized_tender_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def should_use_requirement_extraction_llm_v2(
    settings: Any = app_settings,
    *,
    tender_id: int | None = None,
) -> bool:
    """Return whether a tender should use LLM v2 extraction.

    The existing global flag remains the hard stop. Rollout percentage defaults
    to 100 so current opt-in behavior is preserved unless a narrower rollout is
    configured.
    """

    if not bool(getattr(settings, "requirement_extraction_llm_v2_enabled", False)):
        return False

    blocked_ids = parse_tender_id_set(
        getattr(settings, "requirement_extraction_llm_v2_blocked_tender_ids", "")
    )
    allowlisted_ids = parse_tender_id_set(
        getattr(settings, "requirement_extraction_llm_v2_tender_ids", "")
    )

    if tender_id is not None:
        normalized_tender_id = int(tender_id)
        if normalized_tender_id in blocked_ids:
            return False
        if normalized_tender_id in allowlisted_ids:
            return True
    else:
        normalized_tender_id = None

    rollout_percent = int(getattr(settings, "requirement_extraction_llm_v2_rollout_percent", 100))
    rollout_percent = max(0, min(rollout_percent, 100))
    if rollout_percent >= 100:
        return True
    if rollout_percent <= 0 or normalized_tender_id is None:
        return False
    return requirement_rollout_bucket(normalized_tender_id) < rollout_percent
