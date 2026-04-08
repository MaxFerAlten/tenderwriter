"""FailoverError Classification System.

Ported from OpenClaw's failover-error.ts and error classification pipeline.
Provides structured error types for intelligent fallback decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class FailoverReason(str, Enum):
    """Structured reason for failover decisions."""

    AUTH = "auth"  # 401 - generic auth failure
    AUTH_PERMANENT = "auth_permanent"  # 403 - permanent auth failure
    FORMAT = "format"  # 400 - bad request format
    RATE_LIMIT = "rate_limit"  # 429 - rate limit hit
    OVERLOADED = "overloaded"  # 503 - service overloaded
    BILLING = "billing"  # 402 - out of credits
    TIMEOUT = "timeout"  # 408 - request timeout
    MODEL_NOT_FOUND = "model_not_found"  # 404 - model doesn't exist
    SESSION_EXPIRED = "session_expired"  # 410 - session gone
    UNKNOWN = "unknown"  # unclassified


@dataclass
class FailoverError(Exception):
    """Structured error for fallback decisions.

    Extends Exception with structured fields for intelligent routing.
    """

    reason: FailoverReason
    provider: str
    model: Optional[str] = None
    profile_id: Optional[str] = None
    status: Optional[int] = None
    code: Optional[str] = None
    message: str = ""
    retry_after: Optional[int] = None  # Seconds until retry is allowed

    def __post_init__(self):
        if not self.message and self.code:
            self.message = self.code
        super().__init__(self.message or str(self.reason))

    @property
    def is_transient(self) -> bool:
        """Check if this is a transient error that might succeed on retry."""
        return self.reason in (
            FailoverReason.RATE_LIMIT,
            FailoverReason.OVERLOADED,
            FailoverReason.TIMEOUT,
            FailoverReason.UNKNOWN,
        )

    @property
    def is_persistent(self) -> bool:
        """Check if this is a persistent error requiring longer cooldown."""
        return self.reason in (
            FailoverReason.AUTH,
            FailoverReason.AUTH_PERMANENT,
            FailoverReason.BILLING,
        )

    @property
    def should_never_fallback(self) -> bool:
        """Errors that switching models won't fix."""
        return self.reason in (
            FailoverReason.MODEL_NOT_FOUND,
            FailoverReason.FORMAT,
            FailoverReason.SESSION_EXPIRED,
        )


@dataclass
class FailoverSummaryError(Exception):
    """Raised when all fallback candidates have been exhausted."""

    attempts: List[Dict[str, Any]] = field(default_factory=list)
    soonest_cooldown_expiry: Optional[float] = None
    total_candidates: int = 0

    def __str__(self) -> str:
        reasons = [a.get("reason", "unknown") for a in self.attempts]
        return (
            f"All {self.total_candidates} fallback candidates exhausted. "
            f"Reasons: {reasons}"
        )


def classify_http_status(status: int, message: str = "", code: str = "") -> FailoverReason:
    """Classify HTTP status code into FailoverReason.

    Based on OpenClaw's classifyFailoverSignal() logic.
    """
    # 402 - Payment Required (Anthropic uses this for billing)
    if status == 402:
        if "rate limit" in message.lower() or "quota" in message.lower():
            return FailoverReason.RATE_LIMIT
        return FailoverReason.BILLING

    # 429 - Too Many Requests
    if status == 429:
        return FailoverReason.RATE_LIMIT

    # 401 - Unauthorized
    if status == 401:
        if "billing" in message.lower():
            return FailoverReason.BILLING
        return FailoverReason.AUTH

    # 403 - Forbidden
    if status == 403:
        if "billing" in message.lower() or "credit" in message.lower():
            return FailoverReason.BILLING
        return FailoverReason.AUTH_PERMANENT

    # 408 - Request Timeout
    if status == 408:
        return FailoverReason.TIMEOUT

    # 410 - Gone (session expired)
    if status == 410:
        if "session" in message.lower():
            return FailoverReason.SESSION_EXPIRED
        return FailoverReason.TIMEOUT

    # 503 - Service Unavailable
    if status == 503:
        if "overload" in message.lower() or "busy" in message.lower():
            return FailoverReason.OVERLOADED
        return FailoverReason.TIMEOUT

    # 529 - Server Overloaded (Cloudflare)
    if status == 529:
        return FailoverReason.OVERLOADED

    # 400/422 - Bad Request
    if status in (400, 422):
        if "not found" in message.lower():
            return FailoverReason.MODEL_NOT_FOUND
        return FailoverReason.FORMAT

    # 500/502/504 - Server errors
    if status in (500, 502, 504):
        return FailoverReason.TIMEOUT

    # 404 - Not Found
    if status == 404:
        if "model" in message.lower():
            return FailoverReason.MODEL_NOT_FOUND
        return FailoverReason.UNKNOWN

    return FailoverReason.UNKNOWN


def classify_error_code(code: str, message: str = "") -> Optional[FailoverReason]:
    """Classify provider-specific error codes.

    Many providers use specific error codes instead of HTTP status.
    """
    code_upper = code.upper()
    message_lower = message.lower()

    # Resource exhausted (Anthropic, OpenAI)
    if "RESOURCE_EXHAUSTED" in code_upper or "RESOURCE_LIMIT" in code_upper:
        if "billing" in message_lower or "credit" in message_lower:
            return FailoverReason.BILLING
        return FailoverReason.RATE_LIMIT

    # Rate limit codes
    if "RATE_LIMIT" in code_upper or "TOO_MANY_REQUESTS" in code_upper:
        return FailoverReason.RATE_LIMIT

    # Overloaded
    if "OVERLOADED" in code_upper or "CAPACITY" in code_upper:
        return FailoverReason.OVERLOADED

    # Auth errors
    if "UNAUTHORIZED" in code_upper or "INVALID_API_KEY" in code_upper:
        return FailoverReason.AUTH

    if "FORBIDDEN" in code_upper or "PERMISSION_DENIED" in code_upper:
        return FailoverReason.AUTH_PERMANENT

    # Model not found
    if "NOT_FOUND" in code_upper or "MODEL_NOT" in code_upper:
        return FailoverReason.MODEL_NOT_FOUND

    # Context length (shouldn't fallback)
    if "CONTEXT_LENGTH" in code_upper or "MAX_TOKENS" in code_upper:
        return FailoverReason.FORMAT

    return None


def classify_message_pattern(message: str) -> Optional[FailoverReason]:
    """Classify based on message content patterns.

    Used as a fallback when status/code aren't specific enough.
    """
    message_lower = message.lower()

    # Billing patterns
    if any(
        p in message_lower
        for p in [
            "insufficient credits",
            "out of credits",
            "billing error",
            "payment required",
            "quota exceeded",
            "monthly limit",
        ]
    ):
        return FailoverReason.BILLING

    # Rate limit patterns
    if any(
        p in message_lower
        for p in [
            "rate limit",
            "too many requests",
            "request limit",
            "slow down",
        ]
    ):
        return FailoverReason.RATE_LIMIT

    # Overloaded patterns
    if any(
        p in message_lower
        for p in [
            "overloaded",
            "service unavailable",
            "server busy",
            "try again later",
        ]
    ):
        return FailoverReason.OVERLOADED

    # Auth patterns
    if any(
        p in message_lower
        for p in [
            "invalid api key",
            "unauthorized",
            "authentication failed",
            "invalid token",
        ]
    ):
        return FailoverReason.AUTH

    # Timeout patterns
    if any(
        p in message_lower
        for p in [
            "timeout",
            "timed out",
            "request timeout",
            "connection timeout",
        ]
    ):
        return FailoverReason.TIMEOUT

    return None


def classify_provider_error(
    status: Optional[int] = None,
    code: str = "",
    message: str = "",
    provider: str = "",
) -> FailoverReason:
    """Classify a provider error into a structured FailoverReason.

    Applies OpenClaw's classification pipeline:
    1. HTTP status code
    2. Provider-specific error code
    3. Message pattern matching
    4. Default to UNKNOWN
    """
    # 1. Check HTTP status first (most reliable)
    if status is not None:
        reason = classify_http_status(status, message, code)
        # Special case: 401 with billing message might be billing
        if reason == FailoverReason.AUTH and "billing" in message.lower():
            return FailoverReason.BILLING
        if reason != FailoverReason.UNKNOWN:
            return reason

    # 2. Check error code
    code_reason = classify_error_code(code, message)
    if code_reason is not None:
        return code_reason

    # 3. Check message patterns
    msg_reason = classify_message_pattern(message)
    if msg_reason is not None:
        return msg_reason

    # 4. Provider-specific defaults
    provider_lower = provider.lower()
    if "anthropic" in provider_lower:
        if status == 400 and "invalid" in message.lower():
            return FailoverReason.FORMAT
    elif "openai" in provider_lower:
        if status == 404:
            return FailoverReason.MODEL_NOT_FOUND

    return FailoverReason.UNKNOWN


def coerce_to_failover_error(
    error: Union[Exception, Dict[str, Any], str],
    provider: str = "",
    model: str = "",
    profile_id: Optional[str] = None,
) -> FailoverError:
    """Convert any error into a FailoverError.

    Handles:
    - Existing FailoverError (pass through)
    - Exception objects
    - Dict with error fields
    - Plain strings
    """
    if isinstance(error, FailoverError):
        return error

    if isinstance(error, Exception):
        status = getattr(error, "status", None) or getattr(error, "status_code", None)
        code = getattr(error, "code", "") or ""
        message = str(error)
        error_dict = {}
    elif isinstance(error, dict):
        status = error.get("status") or error.get("status_code")
        code = error.get("code") or ""
        message = error.get("message") or error.get("error", "")
        error_dict = error
    else:
        status = None
        code = ""
        message = str(error)
        error_dict = {}

    reason = classify_provider_error(
        status=status,
        code=code,
        message=message,
        provider=provider,
    )

    return FailoverError(
        reason=reason,
        provider=provider,
        model=model,
        profile_id=profile_id,
        status=status,
        code=code,
        message=message,
        retry_after=error_dict.get("retry_after"),
    )


def is_context_overflow_error(error: FailoverError) -> bool:
    """Check if this is a context overflow error.

    Context overflow errors should NOT trigger fallback - they'd fail on any model.
    """
    if error.reason == FailoverReason.FORMAT:
        return "context" in error.message.lower() or "length" in error.message.lower()
    return False
