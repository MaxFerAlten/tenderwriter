"""Permission checker — decides whether a tool invocation is allowed.

Evaluates permission rules based on the active PermissionMode and any
configured allow/deny rules. Returns ALLOW, DENY, or ASK.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from backend.schemas.permissions import (
    PermissionConfig,
    PermissionDecision,
    PermissionMode,
    PermissionRule,
)
from backend.schemas.tools import RiskLevel

logger = logging.getLogger("tenderclaw.hooks.permissions")

# Default config — can be overridden per-session
_default_config = PermissionConfig()


def check_permission(
    tool_name: str,
    tool_input: dict[str, Any],
    mode: PermissionMode | None = None,
    config: PermissionConfig | None = None,
) -> PermissionDecision:
    """Check whether a tool invocation should be allowed.

    Args:
        tool_name: Name of the tool being invoked.
        tool_input: The tool's input parameters.
        mode: Override permission mode (uses config.mode if None).
        config: Permission config with rules (uses default if None).

    Returns:
        PermissionDecision indicating ALLOW, DENY, or ASK.
    """
    cfg = config or _default_config
    effective_mode = mode or cfg.mode

    # Trust mode: allow everything
    if effective_mode == PermissionMode.TRUST:
        return PermissionDecision.ALLOW

    # Check explicit deny rules first (deny always wins)
    if _matches_any_rule(tool_name, tool_input, cfg.always_deny):
        logger.info("Permission DENY (explicit rule): %s", tool_name)
        return PermissionDecision.DENY

    # Check explicit allow rules
    if _matches_any_rule(tool_name, tool_input, cfg.always_allow):
        return PermissionDecision.ALLOW

    # Auto mode: allow everything not explicitly denied
    if effective_mode == PermissionMode.AUTO:
        return PermissionDecision.ALLOW

    # Plan mode: only allow read-only tools
    if effective_mode == PermissionMode.PLAN:
        # Import here to avoid circular dependency
        from backend.tools.registry import tool_registry

        if tool_registry.has(tool_name):
            tool = tool_registry.get(tool_name)
            if tool.is_read_only:
                return PermissionDecision.ALLOW
        logger.info("Permission DENY (plan mode, non-read-only): %s", tool_name)
        return PermissionDecision.DENY

    # Default mode: ask for medium/high risk, allow low/none
    return _decide_by_risk(tool_name)


def _matches_any_rule(
    tool_name: str,
    tool_input: dict[str, Any],
    rules: list[PermissionRule],
) -> bool:
    """Check if any rule matches the tool name and input pattern."""
    for rule in rules:
        if not fnmatch.fnmatch(tool_name, rule.tool_name):
            continue
        if rule.pattern == "*":
            return True
        # Match pattern against stringified input values
        input_str = " ".join(str(v) for v in tool_input.values())
        if fnmatch.fnmatch(input_str, rule.pattern):
            return True
    return False


def _decide_by_risk(tool_name: str) -> PermissionDecision:
    """In default mode, decide based on tool risk level."""
    from backend.tools.registry import tool_registry

    if not tool_registry.has(tool_name):
        return PermissionDecision.ASK

    tool = tool_registry.get(tool_name)

    if tool.risk_level in (RiskLevel.NONE, RiskLevel.LOW):
        return PermissionDecision.ALLOW

    return PermissionDecision.ASK
