"""Permission schemas — security model for tool execution."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PermissionMode(str, Enum):
    """How the system decides whether to allow tool execution."""

    DEFAULT = "default"      # Ask user for medium/high risk
    AUTO = "auto"            # ML classifier auto-approves (like YOLO)
    PLAN = "plan"            # Read-only tools only, no writes
    TRUST = "trust"          # Approve everything (dangerous)


class PermissionDecision(str, Enum):
    """Result of a permission check."""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionRule(BaseModel):
    """A single permission rule."""

    tool_name: str = "*"
    pattern: str = "*"       # Glob for tool input (e.g., file path)
    decision: PermissionDecision = PermissionDecision.ASK


class PermissionConfig(BaseModel):
    """Permission system configuration."""

    mode: PermissionMode = PermissionMode.DEFAULT
    always_allow: list[PermissionRule] = []
    always_deny: list[PermissionRule] = []
