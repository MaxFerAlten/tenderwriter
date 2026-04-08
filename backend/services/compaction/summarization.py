"""Summarization Pipeline for Compaction.

Ported from OpenClaw's compaction.ts and compaction-safeguard.ts.
Orchestrates the compaction process including summarization.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from backend.services.compaction.identifier import (
    IdentifierPolicy,
    ExtractedIdentifier,
    extract_identifiers,
    filter_high_value_identifiers,
    format_identifier_section,
    generate_identifier_instructions,
    validate_identifier_preservation,
)
from backend.services.compaction.messages import (
    AgentMessage,
    MessageRole,
    collect_tool_failures,
    estimate_messages_tokens,
    repair_tool_pairing,
    split_messages_by_token_share,
    strip_tool_result_details,
    truncate_text,
)
from backend.services.compaction.pruning import (
    DeduplicationStrategy,
    PurgeErrorsStrategy,
    SupersedeWritesStrategy,
    prune_with_strategies,
)
from backend.services.compaction.turn_protection import (
    TurnProtection,
    format_preserved_turns,
    split_preserved_recent_turns,
)

logger = logging.getLogger("tenderclaw.compaction")

# Required sections in summary
REQUIRED_SUMMARY_SECTIONS = [
    "## Decisions",
    "## Open TODOs",
    "## Constraints/Rules",
    "## Pending user asks",
]

# Default summarization instructions
DEFAULT_SUMMARIZATION_INSTRUCTIONS = """You are summarizing a conversation history for an AI coding assistant.

Create a concise summary that captures:
- Key decisions made
- Open tasks and TODOs
- Important constraints or rules established
- Pending user requests
- Relevant file paths, IDs, or identifiers

Be specific and include exact values for identifiers when they are important for continuity.

Format your response with these sections:
## Decisions
## Open TODOs  
## Constraints/Rules
## Pending user asks
## Exact identifiers (preserve these literally)
"""

MERGE_SUMMARIES_INSTRUCTIONS = """You are merging multiple conversation summaries into one.

Take the partial summaries and create a coherent unified summary that preserves all important information.
Keep all ## Decisions, ## Open TODOs, and ## Exact identifiers from all partials.
"""

# Tool failure formatting
MAX_TOOL_FAILURES = 5
MAX_TOOL_FAILURE_CHARS = 200


@dataclass
class CompactionConfig:
    """Configuration for compaction process."""

    enabled: bool = True
    max_context_tokens: int = 16000
    reserve_tokens: int = 2000
    max_history_share: float = 0.5  # Max 50% of context for history
    parts: int = 4  # Number of chunks for large histories

    # Pruning strategies
    deduplication: Optional[DeduplicationStrategy] = None
    supersede_writes: Optional[SupersedeWritesStrategy] = None
    purge_errors: Optional[PurgeErrorsStrategy] = None

    # Turn protection
    turn_protection: Optional[TurnProtection] = None

    # Identifier preservation
    identifier_policy: IdentifierPolicy = IdentifierPolicy.STRICT

    # Summarization
    custom_instructions: Optional[str] = None
    summary_model: Optional[str] = None

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "CompactionConfig":
        """Create from TenderClawConfig."""
        if not config:
            return cls()

        exp = config.get("experimental", {})
        dcp = exp.get("dynamicContextPruning", {})

        return cls(
            enabled=dcp.get("enabled", False),
            max_context_tokens=exp.get("maxContextTokens", 16000),
            reserve_tokens=dcp.get("reserveTokens", 2000),
            max_history_share=dcp.get("maxHistoryShare", 0.5),
            deduplication=DeduplicationStrategy(
                enabled=dcp.get("strategies", {}).get("deduplication", {}).get("enabled", True),
            ),
            supersede_writes=SupersedeWritesStrategy(
                enabled=dcp.get("strategies", {}).get("supersedeWrites", {}).get("enabled", True),
            ),
            purge_errors=PurgeErrorsStrategy(
                enabled=dcp.get("strategies", {}).get("purgeErrors", {}).get("enabled", True),
                error_threshold=dcp.get("strategies", {}).get("purgeErrors", {}).get("turns", 5),
            ),
            turn_protection=TurnProtection(
                enabled=True,
                preserve_recent_turns=dcp.get("turnProtection", {}).get("turns", 3),
            ),
            identifier_policy=IdentifierPolicy(
                dcp.get("identifierPolicy", "strict")
            ),
            custom_instructions=dcp.get("customInstructions"),
        )


@dataclass
class CompactionResult:
    """Result of compaction operation."""

    summary: str
    pruned_messages: List[AgentMessage]
    preserved_messages: List[AgentMessage]
    tokens_saved: int
    stats: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


async def run_compaction(
    messages: List[AgentMessage],
    config: Optional[CompactionConfig] = None,
    summarize_fn: Optional[Callable[[str], Union[str, asyncio.Future]]] = None,
) -> CompactionResult:
    """Run the compaction process.

    Args:
        messages: Conversation history
        config: Compaction configuration
        summarize_fn: Async function to generate summary (or sync callable)

    Returns:
        CompactionResult with summary and metadata
    """
    config = config or CompactionConfig()
    stats: Dict[str, Any] = {}
    errors: List[str] = []

    if not config.enabled:
        return CompactionResult(
            summary="",
            pruned_messages=messages,
            preserved_messages=[],
            tokens_saved=0,
            stats={"skipped": True},
        )

    original_tokens = estimate_messages_tokens(messages)
    stats["original_tokens"] = original_tokens
    stats["original_messages"] = len(messages)

    # Step 1: Prune with strategies
    pruned, prune_stats = prune_with_strategies(
        messages,
        deduplication=config.deduplication,
        supersede_writes=config.supersede_writes,
        purge_errors=config.purge_errors,
    )
    stats["pruning"] = prune_stats

    # Step 2: Repair tool pairing
    repaired, repair_stats = repair_tool_pairing(pruned)
    stats["repair"] = repair_stats

    # Step 3: Split preserved vs summarizable
    preserved, summarizable, turn_stats = split_preserved_recent_turns(
        repaired,
        config.turn_protection,
    )
    stats["turn_protection"] = turn_stats

    # Step 4: Extract identifiers from recent context
    recent_text = "\n".join(
        msg.content for msg in repaired[-50:] if hasattr(msg, "content")
    )
    identifiers = extract_identifiers(recent_text)
    identifiers = filter_high_value_identifiers(identifiers, recent_text)
    stats["identifiers_extracted"] = len(identifiers)

    # Step 5: Check if summarization needed
    summarizable_tokens = estimate_messages_tokens(summarizable)
    budget_tokens = int(config.max_context_tokens * config.max_history_share)

    if summarizable_tokens <= budget_tokens:
        # No summarization needed
        tokens_saved = original_tokens - estimate_messages_tokens(pruned)
        return CompactionResult(
            summary="",
            pruned_messages=pruned,
            preserved_messages=preserved,
            tokens_saved=tokens_saved,
            stats=stats,
        )

    # Step 6: Summarize in stages if needed
    try:
        summary = await summarize_messages(
            summarizable,
            config=config,
            summarize_fn=summarize_fn,
            identifiers=identifiers,
        )
    except Exception as e:
        logger.error(f"Compaction summarization failed: {e}")
        errors.append(str(e))
        summary = "[Compaction failed - original history preserved]"

    # Combine summary with preserved turns
    if preserved:
        preserved_text = format_preserved_turns(preserved)
        final_summary = f"{summary}\n\n{preserved_text}"
    else:
        final_summary = summary

    tokens_saved = original_tokens - (len(summary) // 4)

    return CompactionResult(
        summary=final_summary,
        pruned_messages=pruned,
        preserved_messages=preserved,
        tokens_saved=tokens_saved,
        stats=stats,
        errors=errors,
    )


async def summarize_messages(
    messages: List[AgentMessage],
    config: CompactionConfig,
    summarize_fn: Optional[Callable[[str], Union[str, asyncio.Future]]] = None,
    identifiers: Optional[List[ExtractedIdentifier]] = None,
) -> str:
    """Summarize messages using the configured model.

    For large histories, splits into chunks, summarizes each, then merges.
    """
    if not messages:
        return ""

    if summarize_fn is None:
        # No summarization function - return placeholder
        return "[History truncated - summarization not configured]"

    total_tokens = estimate_messages_tokens(messages)
    max_chunk_tokens = int(config.max_context_tokens * 0.4)  # 40% per chunk

    # Check if splitting needed
    if total_tokens <= max_chunk_tokens or config.parts <= 1:
        return await _summarize_single(
            messages,
            config=config,
            summarize_fn=summarize_fn,
            identifiers=identifiers,
        )

    # Split and summarize in stages
    chunks = split_messages_by_token_share(
        messages,
        parts=config.parts,
        max_context_tokens=config.max_context_tokens,
    )

    partial_summaries: List[str] = []
    for chunk in chunks:
        summary = await _summarize_single(
            chunk,
            config=config,
            summarize_fn=summarize_fn,
            identifiers=None,  # Only include in final merge
        )
        partial_summaries.append(summary)

    # Merge partial summaries
    return await _merge_summaries(
        partial_summaries,
        config=config,
        summarize_fn=summarize_fn,
        identifiers=identifiers,
    )


async def _summarize_single(
    messages: List[AgentMessage],
    config: CompactionConfig,
    summarize_fn: Callable[[str], Union[str, asyncio.Future]],
    identifiers: Optional[List[ExtractedIdentifier]] = None,
) -> str:
    """Summarize a single chunk of messages."""
    # Format messages as text
    messages_text = _format_messages_for_summary(messages)

    # Build prompt
    prompt = _build_summary_prompt(
        messages_text,
        config=config,
        identifiers=identifiers,
    )

    # Call summarization function
    result = summarize_fn(prompt)

    if asyncio.iscoroutine(result):
        result = await result

    return str(result)


async def _merge_summaries(
    partial_summaries: List[str],
    config: CompactionConfig,
    summarize_fn: Callable[[str], Union[str, asyncio.Future]],
    identifiers: Optional[List[ExtractedIdentifier]] = None,
) -> str:
    """Merge multiple partial summaries into one."""
    combined = "\n\n---\n\n".join(partial_summaries)

    prompt = f"""Merge these partial conversation summaries into one unified summary:

{combined}

{MERGE_SUMMARIES_INSTRUCTIONS}

"""

    if identifiers:
        prompt += f"\n{format_identifier_section(identifiers, config.identifier_policy)}"

    if config.custom_instructions:
        prompt += f"\n\n{config.custom_instructions}"

    result = summarize_fn(prompt)

    if asyncio.iscoroutine(result):
        result = await result

    return str(result)


def _format_messages_for_summary(messages: List[AgentMessage]) -> str:
    """Format messages as readable text for summarization."""
    lines = []
    tool_failures = []

    for msg in messages:
        role = msg.role.value

        if msg.role == MessageRole.USER:
            lines.append(f"User: {msg.content}")
        elif msg.role == MessageRole.ASSISTANT:
            content = msg.content
            if msg.tool_calls:
                tc_names = [tc.name for tc in msg.tool_calls]
                content = f"{content}\n[Used tools: {', '.join(tc_names)}]"
            lines.append(f"Assistant: {content}")
        elif msg.role == MessageRole.TOOL_RESULT:
            tool_name = msg.tool_name or "tool"
            content = truncate_text(msg.tool_result_content or msg.content or "", 200)
            if msg.is_error:
                tool_failures.append(f"- {tool_name}: {content}")
            lines.append(f"{tool_name}: {content}")

    result = "\n".join(lines)

    # Append tool failures
    if tool_failures:
        result += "\n\n## Tool Failures\n" + "\n".join(tool_failures[:MAX_TOOL_FAILURES])

    return result


def _build_summary_prompt(
    messages_text: str,
    config: CompactionConfig,
    identifiers: Optional[List[ExtractedIdentifier]] = None,
) -> str:
    """Build the summarization prompt."""
    prompt = f"""Summarize this conversation history:

{messages_text}

"""

    prompt += DEFAULT_SUMMARIZATION_INSTRUCTIONS + "\n"

    prompt += generate_identifier_instructions(config.identifier_policy) + "\n"

    if identifiers:
        prompt += f"\n{format_identifier_section(identifiers, config.identifier_policy)}"

    if config.custom_instructions:
        prompt += f"\n\nAdditional instructions:\n{config.custom_instructions}"

    return prompt


def validate_summary_quality(
    summary: str,
    identifiers: List[ExtractedIdentifier],
    policy: IdentifierPolicy,
) -> tuple[bool, List[str]]:
    """Validate summary quality."""
    violations: List[str] = []

    # Check required sections
    for section in REQUIRED_SUMMARY_SECTIONS:
        if section not in summary:
            violations.append(f"missing_section:{section}")

    # Check identifier preservation
    if policy == IdentifierPolicy.STRICT:
        valid, id_violations = validate_identifier_preservation(
            summary, identifiers, policy
        )
        violations.extend([f"missing_identifier:{v}" for v in id_violations])

    return len(violations) == 0, violations
