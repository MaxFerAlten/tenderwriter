"""TenderClaw Configuration System.

Hierarchical config management with Pydantic validation.
Supports JSON, JSONC, YAML, and environment variables.
"""

from backend.tenderclaw_config.jsonc import (
    load_jsonc,
    loads_jsonc,
    merge_jsonc,
    strip_jsonc_comments,
    validate_jsonc,
)
from backend.tenderclaw_config.manager import (
    ConfigManager,
    ConfigSource,
    config_manager,
    get_config_manager,
)

__all__ = [
    "ConfigManager",
    "ConfigSource",
    "config_manager",
    "get_config_manager",
    "load_jsonc",
    "loads_jsonc",
    "merge_jsonc",
    "strip_jsonc_comments",
    "validate_jsonc",
]
