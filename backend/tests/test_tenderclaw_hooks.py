"""Tests for hooks."""

import pytest

from backend.hooks import HookContext, HookEvent, HookRegistry
from backend.hooks.handlers import (
    KeywordDetectorHook,
    RalphLoopHook,
    SessionRecoveryHook,
)


class TestKeywordDetectorHook:
    """Tests for keyword detector hook."""

    @pytest.mark.asyncio
    async def test_detect_ultrawork(self):
        """Test detecting ultrawork keyword."""
        hook = KeywordDetectorHook()
        context = HookContext(
            event=HookEvent.MESSAGE_RECEIVED,
            message="Run ultrawork on this task"
        )
        result = await hook.execute(context)
        assert result.handled is True
        assert "ultrawork" in result.metadata.get("keywords_found", [])

    @pytest.mark.asyncio
    async def test_detect_analyze(self):
        """Test detecting analyze keyword."""
        hook = KeywordDetectorHook()
        context = HookContext(
            event=HookEvent.MESSAGE_RECEIVED,
            message="Analyze this code"
        )
        result = await hook.execute(context)
        assert result.handled is True
        assert "analyze" in result.metadata.get("keywords_found", [])

    @pytest.mark.asyncio
    async def test_no_detection(self):
        """Test no detection for normal message."""
        hook = KeywordDetectorHook()
        context = HookContext(
            event=HookEvent.MESSAGE_RECEIVED,
            message="Hello, how are you?"
        )
        result = await hook.execute(context)
        assert result.handled is False


class TestRalphLoopHook:
    """Tests for Ralph loop hook."""

    def test_start_stop_loop(self):
        """Test starting and stopping loop."""
        hook = RalphLoopHook()
        assert hook.is_active is False
        
        hook.start_loop(max_iterations=10)
        assert hook.is_active is True
        
        hook.stop_loop()
        assert hook.is_active is False

    @pytest.mark.asyncio
    async def test_completion_detection(self):
        """Test detecting completion marker."""
        hook = RalphLoopHook()
        hook.start_loop()
        
        context = HookContext(
            event=HookEvent.MESSAGE_RECEIVED,
            message="Work completed <promise>DONE</promise>"
        )
        result = await hook.execute(context)
        
        assert result.handled is True
        assert result.metadata.get("completed") is True
        assert hook.is_active is False

    @pytest.mark.asyncio
    async def test_max_iterations(self):
        """Test max iterations reached."""
        hook = RalphLoopHook()
        hook.start_loop(max_iterations=2)
        hook.current_iteration = 2
        
        context = HookContext(event=HookEvent.SESSION_IDLE)
        result = await hook.execute(context)
        
        assert result.handled is True
        assert result.metadata.get("max_reached") is True


class TestSessionRecoveryHook:
    """Tests for session recovery hook."""

    @pytest.mark.asyncio
    async def test_recover_from_context_window(self):
        """Test recovery from context window error."""
        hook = SessionRecoveryHook()
        context = HookContext(
            event=HookEvent.SESSION_ERROR,
            metadata={"error": "context_window_exceeded"}
        )
        result = await hook.execute(context)
        
        assert result.handled is True
        assert result.metadata.get("strategy") == "compact_context"

    @pytest.mark.asyncio
    async def test_recover_from_rate_limit(self):
        """Test recovery from rate limit."""
        hook = SessionRecoveryHook()
        context = HookContext(
            event=HookEvent.SESSION_ERROR,
            metadata={"error": "rate_limit_exceeded"}
        )
        result = await hook.execute(context)
        
        assert result.handled is True
        assert result.metadata.get("strategy") == "wait_and_retry"

    @pytest.mark.asyncio
    async def test_no_recovery_needed(self):
        """Test no recovery for unknown error."""
        hook = SessionRecoveryHook()
        context = HookContext(
            event=HookEvent.SESSION_ERROR,
            metadata={"error": "some unknown error"}
        )
        result = await hook.execute(context)
        
        assert result.handled is False
