"""Tests for Compaction System.

Tests token estimation, message splitting, pruning, and summarization.
"""

import pytest

from backend.services.compaction import (
    AgentMessage,
    CompactionConfig,
    DeduplicationStrategy,
    MessageRole,
    PurgeErrorsStrategy,
    SupersedeWritesStrategy,
    ToolCall,
    TurnProtection,
    extract_identifiers,
    estimate_tokens,
    prune_with_strategies,
    repair_tool_pairing,
    run_compaction,
    split_messages_by_token_share,
    split_preserved_recent_turns,
    strip_tool_result_details,
    IdentifierPolicy,
    validate_identifier_preservation,
)


class TestTokenEstimation:
    """Tests for token estimation."""

    def test_estimate_tokens_empty(self):
        """Empty text returns 0."""
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_estimate_tokens_basic(self):
        """Basic text estimation."""
        text = "hello world"
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert tokens < len(text)  # Tokens < chars for short text

    def test_estimate_tokens_long(self):
        """Long text estimation."""
        text = " ".join(["word"] * 100)
        tokens = estimate_tokens(text)
        assert tokens > 50  # At least half the word count


class TestMessageHandling:
    """Tests for message types and handling."""

    def test_strip_tool_result_details(self):
        """Should strip tool result details for security."""
        messages = [
            AgentMessage(role=MessageRole.USER, content="Hello"),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="result content",
                tool_call_id="123",
                tool_name="test",
            ),
        ]
        stripped = strip_tool_result_details(messages)
        assert len(stripped) == 2

    def test_repair_tool_pairing(self):
        """Should repair tool use/result pairing."""
        messages = [
            AgentMessage(
                role=MessageRole.ASSISTANT,
                content="Using tool",
                tool_calls=[ToolCall(id="tc1", name="test", input={})],
            ),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="result",
                tool_call_id="tc1",
                tool_name="test",
            ),
        ]
        repaired, stats = repair_tool_pairing(messages)
        assert len(repaired) == 2
        assert stats["added_synthetic"] == 0

    def test_repair_missing_tool_result(self):
        """Should add synthetic error for missing tool result."""
        messages = [
            AgentMessage(
                role=MessageRole.ASSISTANT,
                content="Using tool",
                tool_calls=[ToolCall(id="tc1", name="test", input={})],
            ),
            # Missing tool result!
        ]
        repaired, stats = repair_tool_pairing(messages)
        assert len(repaired) == 2  # Assistant + synthetic
        assert stats["added_synthetic"] == 1


class TestPruningStrategies:
    """Tests for pruning strategies."""

    def test_deduplication_basic(self):
        """Should deduplicate identical tool results."""
        strategy = DeduplicationStrategy(enabled=True)
        messages = [
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same content",
                tool_call_id="tc1",
                tool_name="read",
            ),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same content",
                tool_call_id="tc2",
                tool_name="read",
            ),
        ]
        pruned, stats = strategy.apply(messages)
        assert stats["removed"] >= 1

    def test_deduplication_disabled(self):
        """Should not deduplicate when disabled."""
        strategy = DeduplicationStrategy(enabled=False)
        messages = [
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same content",
                tool_call_id="tc1",
                tool_name="read",
            ),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same content",
                tool_call_id="tc2",
                tool_name="read",
            ),
        ]
        pruned, stats = strategy.apply(messages)
        assert stats["removed"] == 0
        assert len(pruned) == 2

    def test_purge_errors(self):
        """Should purge old errors after threshold."""
        strategy = PurgeErrorsStrategy(
            enabled=True,
            error_threshold=2,
            keep_recent=1,
        )
        messages = [
            AgentMessage(role=MessageRole.USER, content="msg1"),
            AgentMessage(role=MessageRole.ASSISTANT, content="resp1"),
            AgentMessage(role=MessageRole.USER, content="msg2"),
            AgentMessage(role=MessageRole.ASSISTANT, content="resp2"),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="error1",
                is_error=True,
                tool_name="test",
            ),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="error2",
                is_error=True,
                tool_name="test",
            ),
        ]
        pruned, stats = strategy.apply(messages)
        # With 2 successful turns, errors should be considered for purge
        assert len(pruned) >= 4  # At least user/assistant pairs


class TestTurnProtection:
    """Tests for turn protection."""

    def test_split_preserved_turns(self):
        """Should preserve recent turns."""
        config = TurnProtection(
            enabled=True,
            preserve_recent_turns=2,
        )
        messages = [
            AgentMessage(role=MessageRole.USER, content="old user"),
            AgentMessage(role=MessageRole.ASSISTANT, content="old assistant"),
            AgentMessage(role=MessageRole.USER, content="recent user"),
            AgentMessage(role=MessageRole.ASSISTANT, content="recent assistant"),
        ]
        preserved, summarizable, stats = split_preserved_recent_turns(messages, config)

        assert stats["preserved_turns"] == 2
        assert stats["summarizable_count"] == 2

    def test_split_disabled(self):
        """Should not split when disabled."""
        config = TurnProtection(enabled=False)
        messages = [
            AgentMessage(role=MessageRole.USER, content="user"),
            AgentMessage(role=MessageRole.ASSISTANT, content="assistant"),
        ]
        preserved, summarizable, stats = split_preserved_recent_turns(messages, config)

        # When disabled, preserved is empty, summarizable has all
        assert len(preserved) == 0
        assert len(summarizable) == 2


class TestIdentifierPreservation:
    """Tests for identifier extraction and preservation."""

    def test_extract_urls(self):
        """Should extract URLs."""
        text = "Check https://example.com/path for details"
        identifiers = extract_identifiers(text)
        urls = [i.value for i in identifiers if i.value.startswith("http")]
        assert len(urls) >= 1

    def test_extract_file_paths(self):
        """Should extract file paths."""
        text = "File: /path/to/file.py exists"
        identifiers = extract_identifiers(text)
        paths = [i for i in identifiers if "/" in i.value or "\\" in i.value]
        assert len(paths) >= 1

    def test_extract_git_hashes(self):
        """Should extract git hashes."""
        text = "Commit abc123def456789 created"
        identifiers = extract_identifiers(text)
        hashes = [i for i in identifiers if len(i.value) >= 8 and all(c in "0123456789abcdef" for c in i.value.lower())]
        assert len(hashes) >= 1

    def test_validate_strict_preservation(self):
        """Strict mode should fail if identifier missing."""
        identifiers = [
            type("Id", (), {"value": "https://example.com", "normalized": "https://example.com"})(),
        ]
        summary_with = "See https://example.com for info"
        summary_without = "See the link for info"

        valid_with, _ = validate_identifier_preservation(
            summary_with, identifiers, IdentifierPolicy.STRICT
        )
        valid_without, violations = validate_identifier_preservation(
            summary_without, identifiers, IdentifierPolicy.STRICT
        )

        assert valid_with is True
        assert valid_without is False
        assert len(violations) >= 1


class TestCompactionConfig:
    """Tests for compaction configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = CompactionConfig()
        assert config.enabled is True
        assert config.max_context_tokens == 16000
        assert config.reserve_tokens == 2000
        assert config.max_history_share == 0.5
        # Strategies default to None when not enabled
        assert config.deduplication is None
        assert config.turn_protection is None

    def test_from_config(self):
        """Should parse from TenderClawConfig."""
        config_dict = {
            "experimental": {
                "dynamicContextPruning": {
                    "enabled": True,
                    "maxHistoryShare": 0.6,
                    "turnProtection": {
                        "turns": 5,
                    },
                }
            }
        }
        config = CompactionConfig.from_config(config_dict)
        assert config.enabled is True
        assert config.max_history_share == 0.6
        assert config.turn_protection.preserve_recent_turns == 5


class TestPruneWithStrategies:
    """Tests for combined pruning."""

    def test_combined_pruning(self):
        """Should apply multiple strategies."""
        messages = [
            AgentMessage(role=MessageRole.USER, content="Hello"),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same",
                tool_call_id="tc1",
                tool_name="test",
            ),
            AgentMessage(
                role=MessageRole.TOOL_RESULT,
                content="same",
                tool_call_id="tc2",
                tool_name="test",
            ),
        ]

        result, stats = prune_with_strategies(
            messages,
            deduplication=DeduplicationStrategy(enabled=True),
        )

        assert stats["total_original"] == 3
        assert stats["total_final"] <= 3
        assert "deduplication" in stats["strategies_applied"]


class TestSplitMessagesByTokenShare:
    """Tests for message splitting."""

    def test_split_empty(self):
        """Should handle empty messages."""
        result = split_messages_by_token_share([])
        assert result == []

    def test_split_small(self):
        """Should not split small message lists."""
        messages = [
            AgentMessage(role=MessageRole.USER, content="Hi"),
            AgentMessage(role=MessageRole.ASSISTANT, content="Hello"),
        ]
        result = split_messages_by_token_share(messages, parts=4)
        # Should return individual messages or small chunks
        total = sum(len(chunk) for chunk in result)
        assert total == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
