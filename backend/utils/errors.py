"""Custom exception hierarchy for TenderClaw.

Every exception inherits from TenderClawError so callers can catch broadly.
"""

from __future__ import annotations


class TenderClawError(Exception):
    """Base exception for all TenderClaw errors."""


class SessionNotFoundError(TenderClawError):
    """Raised when a session ID does not exist."""


class ToolExecutionError(TenderClawError):
    """Raised when a tool fails during execution."""


class ToolNotFoundError(TenderClawError):
    """Raised when a requested tool is not registered."""


class ProviderError(TenderClawError):
    """Raised when an AI provider API call fails."""


class PermissionDeniedError(TenderClawError):
    """Raised when a tool use is denied by the permission system."""


class HookBailError(TenderClawError):
    """Raised when a hook bails out of the execution pipeline."""
