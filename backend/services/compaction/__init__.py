"""Compaction System for Conversation History.

Opt-in alternative for compressing conversation history.
Implements OpenClaw-style deduplication, supersede writes,
purge errors, turn protection, and summarization.

Enable via TenderClawConfig:
    experimental:
        dynamic_context_pruning:
            enabled: true
"""

from backend.services.compaction.messages import (
    AgentMessage,
    MessageRole,
    ToolCall,
    ToolResult,
    estimate_tokens,
    split_messages_by_token_share,
    repair_tool_pairing,
    strip_tool_result_details,
)
from backend.services.compaction.pruning import (
    DeduplicationStrategy,
    SupersedeWritesStrategy,
    PurgeErrorsStrategy,
    prune_with_strategies,
)
from backend.services.compaction.turn_protection import (
    TurnProtection,
    split_preserved_recent_turns,
)
from backend.services.compaction.identifier import (
    IdentifierPolicy,
    extract_identifiers,
    validate_identifier_preservation,
)
from backend.services.compaction.summarization import (
    CompactionConfig,
    CompactionResult,
    run_compaction,
    summarize_messages,
)

__all__ = [
    "AgentMessage",
    "MessageRole",
    "ToolCall",
    "ToolResult",
    "estimate_tokens",
    "split_messages_by_token_share",
    "repair_tool_pairing",
    "strip_tool_result_details",
    "DeduplicationStrategy",
    "SupersedeWritesStrategy",
    "PurgeErrorsStrategy",
    "prune_with_strategies",
    "TurnProtection",
    "split_preserved_recent_turns",
    "IdentifierPolicy",
    "extract_identifiers",
    "validate_identifier_preservation",
    "CompactionConfig",
    "CompactionResult",
    "run_compaction",
    "summarize_messages",
]
