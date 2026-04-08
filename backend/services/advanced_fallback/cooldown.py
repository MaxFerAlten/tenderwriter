"""Two-Lane Cooldown System.

Ported from OpenClaw's cooldown/probe logic.
Implements transient vs persistent cooldown lanes with backoff strategies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

from backend.services.advanced_fallback.errors import FailoverReason

# Transient cooldown backoff: 30s → 60s → 5min (capped)
TRANSIENT_COOLDOWN_STEPS = [
    30_000,  # 30 seconds
    60_000,  # 1 minute
    300_000,  # 5 minutes (max)
]

# Persistent cooldown backoff policies (base * 2^error_count)
COOLDOWN_POLICIES = {
    FailoverReason.BILLING: {
        "base_ms": 5 * 60 * 60 * 1000,  # 5 hours
        "max_ms": 24 * 60 * 60 * 1000,  # 24 hours
    },
    FailoverReason.AUTH_PERMANENT: {
        "base_ms": 10 * 60 * 1000,  # 10 minutes
        "max_ms": 60 * 60 * 1000,  # 60 minutes
    },
    FailoverReason.AUTH: {
        "base_ms": 5 * 60 * 1000,  # 5 minutes
        "max_ms": 30 * 60 * 1000,  # 30 minutes
    },
}

# Probe throttling
MIN_PROBE_INTERVAL_MS = 30_000  # 30 seconds between probes
PROBE_MARGIN_MS = 2 * 60 * 1000  # Probe when within 2 min of expiry
PROBE_STATE_TTL_MS = 24 * 60 * 60 * 1000  # Clean stale entries daily


@dataclass
class TwoLaneCooldown:
    """Two-lane cooldown system for auth profiles.

    Lane 1 (Transient): rate_limit, overloaded, timeout, unknown
    Lane 2 (Persistent): billing, auth_permanent, auth

    Each lane has its own backoff strategy and recovery behavior.
    """

    transient_cooldown_ms: int = 0
    persistent_cooldown_ms: int = 0
    transient_reason: Optional[FailoverReason] = None
    persistent_reason: Optional[FailoverReason] = None
    error_count: int = 0
    last_failure_at: Optional[float] = None

    def calculate_transient_cooldown(self, error_count: Optional[int] = None) -> int:
        """Calculate transient cooldown based on error count.

        Uses stepped backoff: 30s → 60s → 5min (capped)
        """
        count = error_count if error_count is not None else self.error_count
        index = min(count, len(TRANSIENT_COOLDOWN_STEPS) - 1)
        return TRANSIENT_COOLDOWN_STEPS[index]

    def calculate_persistent_cooldown(self, reason: FailoverReason, error_count: Optional[int] = None) -> int:
        """Calculate persistent cooldown using exponential backoff.

        Formula: min(base * 2^error_count, max)
        """
        policy = COOLDOWN_POLICIES.get(reason)
        if not policy:
            return policy.get("max_ms", 60 * 60 * 1000)

        count = error_count if error_count is not None else self.error_count
        base_ms = policy["base_ms"]
        max_ms = policy["max_ms"]

        cooldown = base_ms * (2 ** count)
        return min(cooldown, max_ms)

    def apply_transient_cooldown(self, reason: FailoverReason, error_count: int) -> float:
        """Apply transient cooldown. Returns expiry timestamp."""
        self.transient_reason = reason
        self.error_count = error_count
        self.transient_cooldown_ms = self.calculate_transient_cooldown(error_count)
        self.last_failure_at = time.time()
        return time.time() + self.transient_cooldown_ms / 1000

    def apply_persistent_cooldown(self, reason: FailoverReason, error_count: int) -> float:
        """Apply persistent cooldown. Returns expiry timestamp."""
        self.persistent_reason = reason
        self.error_count = error_count
        self.persistent_cooldown_ms = self.calculate_persistent_cooldown(reason, error_count)
        self.last_failure_at = time.time()
        return time.time() + self.persistent_cooldown_ms / 1000

    def clear_transient(self) -> None:
        """Clear transient cooldown (but keep error count for backoff)."""
        self.transient_cooldown_ms = 0
        self.transient_reason = None

    def clear_all(self) -> None:
        """Clear all cooldowns and reset error count."""
        self.transient_cooldown_ms = 0
        self.persistent_cooldown_ms = 0
        self.transient_reason = None
        self.persistent_reason = None
        self.error_count = 0
        self.last_failure_at = None

    def is_in_transient_cooldown(self, now: Optional[float] = None) -> bool:
        """Check if in transient cooldown."""
        if self.transient_cooldown_ms <= 0:
            return False
        now = now or time.time()
        return now < (self.last_failure_at or 0) + self.transient_cooldown_ms / 1000

    def is_in_persistent_cooldown(self, now: Optional[float] = None) -> bool:
        """Check if in persistent cooldown."""
        if self.persistent_cooldown_ms <= 0:
            return False
        now = now or time.time()
        return now < (self.last_failure_at or 0) + self.persistent_cooldown_ms / 1000

    def is_usable(self, now: Optional[float] = None) -> bool:
        """Check if profile is usable (not in any cooldown)."""
        return not self.is_in_transient_cooldown(now) and not self.is_in_persistent_cooldown(now)

    def unusable_until(self, now: Optional[float] = None) -> float:
        """Get earliest time profile becomes usable."""
        now = now or time.time()
        times = []

        if self.is_in_transient_cooldown(now):
            times.append((self.last_failure_at or 0) + self.transient_cooldown_ms / 1000)

        if self.is_in_persistent_cooldown(now):
            times.append((self.last_failure_at or 0) + self.persistent_cooldown_ms / 1000)

        return max(times) if times else now

    def should_bypass_model_cooldown(
        self,
        cooldown_model: Optional[str],
        requested_model: Optional[str],
    ) -> bool:
        """Check if model-scoped cooldown should be bypassed.

        If cooldown was caused by rate_limit on model A, and we're
        requesting model B, allow it.
        """
        if not self.transient_reason == FailoverReason.RATE_LIMIT:
            return False
        if not cooldown_model or not requested_model:
            return False
        if cooldown_model == requested_model:
            return False
        # Different model - allow
        return True


def calculate_transient_cooldown(error_count: int) -> int:
    """Standalone function for calculating transient cooldown."""
    index = min(error_count, len(TRANSIENT_COOLDOWN_STEPS) - 1)
    return TRANSIENT_COOLDOWN_STEPS[index]


def calculate_persistent_cooldown(reason: FailoverReason, error_count: int) -> int:
    """Standalone function for calculating persistent cooldown."""
    policy = COOLDOWN_POLICIES.get(reason)
    if not policy:
        return 60 * 60 * 1000  # Default 1 hour

    base_ms = policy["base_ms"]
    max_ms = policy["max_ms"]

    cooldown = base_ms * (2 ** error_count)
    return min(cooldown, max_ms)


@dataclass
class CooldownDecision:
    """Decision on whether to attempt a request during cooldown."""

    type: Literal["attempt", "skip", "probe"]
    reason: Optional[str] = None
    error: Optional[str] = None
    mark_probe: bool = False


def resolve_cooldown_decision(
    reason: FailoverReason,
    is_primary: bool,
    has_fallback_candidates: bool,
    cooldown_expiry: Optional[float],
    requested_now: bool,
    last_probe_at: Optional[float],
    now: Optional[float] = None,
) -> CooldownDecision:
    """Resolve whether to attempt, skip, or probe during cooldown.

    Based on OpenClaw's resolveCooldownDecision() logic.
    """
    now = now or time.time()

    # Persistent issues: never probe, just skip
    if reason in (FailoverReason.AUTH, FailoverReason.AUTH_PERMANENT):
        return CooldownDecision(
            type="skip",
            reason=reason.value,
            error=f"Persistent failure ({reason.value}) - requires manual intervention",
        )

    # Billing: special handling
    if reason == FailoverReason.BILLING:
        # Single-provider setup: probe when requested
        if is_primary and not has_fallback_candidates:
            if _is_probe_throttle_open(last_probe_at, now):
                return CooldownDecision(
                    type="attempt",
                    reason=reason.value,
                    mark_probe=True,
                )
            return CooldownDecision(
                type="skip",
                reason=reason.value,
                error="Billing issue - waiting for cooldown expiry",
            )

        # Multi-fallback: probe near expiry
        if cooldown_expiry:
            time_until_expiry = cooldown_expiry - now
            if time_until_expiry <= PROBE_MARGIN_MS / 1000:
                if _is_probe_throttle_open(last_probe_at, now):
                    return CooldownDecision(
                        type="attempt",
                        reason=reason.value,
                        mark_probe=True,
                    )

        return CooldownDecision(
            type="skip",
            reason=reason.value,
            error="Billing issue - waiting for fallback candidates or cooldown",
        )

    # Transient issues: probe near expiry OR when explicitly requested
    if cooldown_expiry:
        time_until_expiry = cooldown_expiry - now

        if requested_now and is_primary:
            # Explicit request on primary: allow
            return CooldownDecision(
                type="attempt",
                reason=reason.value,
            )

        if time_until_expiry <= PROBE_MARGIN_MS / 1000:
            # Near expiry: probe
            if _is_probe_throttle_open(last_probe_at, now):
                return CooldownDecision(
                    type="attempt",
                    reason=reason.value,
                    mark_probe=True,
                )

    # Same-provider fallbacks: relax cooldown for transient issues
    if not is_primary and reason in (
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.UNKNOWN,
    ):
        return CooldownDecision(
            type="attempt",
            reason=reason.value,
        )

    return CooldownDecision(
        type="skip",
        reason=reason.value,
        error=f"Transient failure ({reason.value}) - waiting for cooldown",
    )


def _is_probe_throttle_open(last_probe_at: Optional[float], now: float) -> bool:
    """Check if probe throttling allows a new probe."""
    if last_probe_at is None:
        return True
    return (now * 1000 - last_probe_at * 1000) >= MIN_PROBE_INTERVAL_MS


def clear_expired_cooldowns(
    stats: Dict[str, Any],
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Clear expired cooldowns from stats dict.

    Returns updated stats with expired cooldowns removed.
    """
    now = now or time.time()
    updated = dict(stats)

    # Clear expired transient cooldown
    cooldown_until = updated.get("cooldownUntil")
    if cooldown_until and now >= cooldown_until:
        updated.pop("cooldownUntil", None)
        updated.pop("cooldownReason", None)
        updated.pop("cooldownModel", None)

    # Clear expired persistent cooldown
    disabled_until = updated.get("disabledUntil")
    if disabled_until and now >= disabled_until:
        updated.pop("disabledUntil", None)
        updated.pop("disabledReason", None)

    # Reset error counts when all cooldowns cleared (circuit breaker reset)
    unusable_until = updated.get("cooldownUntil") or updated.get("disabledUntil")
    if not unusable_until:
        if updated.get("errorCount", 0) > 0:
            updated["errorCount"] = 0
            updated.pop("failureCounts", None)

    return updated


def should_preserve_probe_slot(
    reason: FailoverReason,
) -> bool:
    """Check if probe failure should preserve the transient probe slot.

    Some failures indicate the issue isn't transient - don't consume
    the probe slot for other candidates.
    """
    return reason in (
        FailoverReason.MODEL_NOT_FOUND,
        FailoverReason.FORMAT,
        FailoverReason.AUTH,
        FailoverReason.AUTH_PERMANENT,
        FailoverReason.SESSION_EXPIRED,
    )


def should_use_transient_probe_slot(reason: FailoverReason) -> bool:
    """Check if this reason should use the transient probe slot.

    Billing uses a separate slot.
    """
    return reason in (
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.UNKNOWN,
    )
