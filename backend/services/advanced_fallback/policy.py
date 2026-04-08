"""Fallback Policy Decision Logic.

Ported from OpenClaw's failover-policy.ts.
Determines whether to rotate profiles, fallback models, or surface errors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set

from backend.services.advanced_fallback.errors import FailoverReason


class FallbackDecisionAction(str, Enum):
    """Actions from fallback policy decisions."""

    CONTINUE_NORMAL = "continue_normal"
    ROTATE_PROFILE = "rotate_profile"
    FALLBACK_MODEL = "fallback_model"
    SURFACE_ERROR = "surface_error"
    RETURN_ERROR_PAYLOAD = "return_error_payload"


@dataclass
class FallbackDecision:
    """Decision from the fallback policy."""

    action: FallbackDecisionAction
    reason: Optional[FailoverReason] = None
    profile_rotated: bool = False


class Stage(str, Enum):
    """Current retry stage."""

    PROMPT = "prompt"  # Initial request
    ASSISTANT = "assistant"  # Response generation
    RETRY_LIMIT = "retry_limit"  # Exhausted retries


@dataclass
class FallbackPolicy:
    """Policy configuration for fallback behavior."""

    max_profile_retries: int = 2
    max_model_retries: int = 3
    fallback_enabled: bool = True

    @classmethod
    def from_config(cls, config: Optional[dict] = None) -> FallbackPolicy:
        """Create policy from config dict."""
        if not config:
            return cls()
        return cls(
            max_profile_retries=config.get("maxProfileRetries", 2),
            max_model_retries=config.get("maxModelRetries", 3),
            fallback_enabled=config.get("fallbackEnabled", True),
        )


def should_escalate_retry_limit(reason: Optional[FailoverReason]) -> bool:
    """Determine if retry limit should escalate to model fallback.

    Only escalate errors that might be fixed by switching models.
    """
    if reason is None:
        return False

    # These errors won't be fixed by switching models
    if reason in (
        FailoverReason.TIMEOUT,  # Timeouts may recover on same model
        FailoverReason.MODEL_NOT_FOUND,  # Model doesn't exist anywhere
        FailoverReason.FORMAT,  # Request format issue
        FailoverReason.SESSION_EXPIRED,  # Session issue, not model
    ):
        return False

    return True


def should_rotate_on_prompt_error(
    reason: FailoverReason,
    profile_rotated: bool,
) -> bool:
    """Determine if profile should rotate on prompt/stage error."""
    if profile_rotated:
        return False

    # Rotate on transient errors
    if reason in (
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.UNKNOWN,
    ):
        return True

    # Rotate on timeout if haven't tried others
    if reason == FailoverReason.TIMEOUT:
        return True

    return False


def should_rotate_on_assistant_error(
    reason: FailoverReason,
    profile_rotated: bool,
    fallback_configured: bool,
) -> bool:
    """Determine if profile should rotate on assistant/response error."""
    if profile_rotated:
        return False

    # Always rotate on transient errors if not already rotated
    if reason in (
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.TIMEOUT,
        FailoverReason.UNKNOWN,
    ):
        return True

    return False


def resolve_fallback_decision(
    stage: Stage,
    reason: Optional[FailoverReason],
    profile_rotated: bool,
    fallback_configured: bool,
    retry_count: int,
    max_retries: int,
    policy: Optional[FallbackPolicy] = None,
) -> FallbackDecision:
    """Resolve the fallback decision based on current state.

    Based on OpenClaw's resolveRunFailoverDecision() logic.
    """
    policy = policy or FallbackPolicy()

    # Stage 1: Retry limit reached
    if stage == Stage.RETRY_LIMIT:
        if (
            policy.fallback_enabled
            and fallback_configured
            and should_escalate_retry_limit(reason)
        ):
            return FallbackDecision(
                action=FallbackDecisionAction.FALLBACK_MODEL,
                reason=reason,
            )
        return FallbackDecision(
            action=FallbackDecisionAction.RETURN_ERROR_PAYLOAD,
            reason=reason,
        )

    # Stage 2: Prompt error
    if stage == Stage.PROMPT:
        if not profile_rotated and should_rotate_on_prompt_error(reason or FailoverReason.UNKNOWN, profile_rotated):
            return FallbackDecision(
                action=FallbackDecisionAction.ROTATE_PROFILE,
                reason=reason,
                profile_rotated=True,
            )

        if policy.fallback_enabled and fallback_configured and reason:
            return FallbackDecision(
                action=FallbackDecisionAction.FALLBACK_MODEL,
                reason=reason,
            )

        return FallbackDecision(
            action=FallbackDecisionAction.SURFACE_ERROR,
            reason=reason,
        )

    # Stage 3: Assistant error
    if stage == Stage.ASSISTANT:
        if not profile_rotated and should_rotate_on_assistant_error(
            reason or FailoverReason.UNKNOWN,
            profile_rotated,
            policy.fallback_enabled,
        ):
            return FallbackDecision(
                action=FallbackDecisionAction.ROTATE_PROFILE,
                reason=reason,
                profile_rotated=True,
            )

        if policy.fallback_enabled and fallback_configured:
            return FallbackDecision(
                action=FallbackDecisionAction.FALLBACK_MODEL,
                reason=reason,
            )

        return FallbackDecision(
            action=FallbackDecisionAction.CONTINUE_NORMAL,
            reason=reason,
        )

    # Unknown stage - continue normally
    return FallbackDecision(
        action=FallbackDecisionAction.CONTINUE_NORMAL,
        reason=reason,
    )


def is_context_overflow(reason: FailoverReason, message: str) -> bool:
    """Check if this is a context overflow error.

    Context overflow errors should NOT trigger fallback - they'd fail on any model.
    These should be surfaced immediately to the user.
    """
    if reason == FailoverReason.FORMAT:
        return "context" in message.lower() or "length" in message.lower()
    return False


def should_never_fallback(reason: FailoverReason) -> bool:
    """Errors that switching models won't fix.

    These should surface immediately without attempting fallback.
    """
    return reason in (
        FailoverReason.MODEL_NOT_FOUND,
        FailoverReason.FORMAT,
        FailoverReason.SESSION_EXPIRED,
    )


def get_escalation_reasons() -> Set[FailoverReason]:
    """Get reasons that should escalate to model fallback."""
    return {
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.BILLING,
        FailoverReason.AUTH,
        FailoverReason.AUTH_PERMANENT,
        FailoverReason.UNKNOWN,
    }


def get_rotation_reasons() -> Set[FailoverReason]:
    """Get reasons that should trigger profile rotation before fallback."""
    return {
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.TIMEOUT,
        FailoverReason.UNKNOWN,
    }
