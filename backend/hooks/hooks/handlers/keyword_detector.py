"""Keyword detector hook."""

from __future__ import annotations

import re
from typing import Any

from hooks import BaseHook, HookContext, HookEvent, HookResult


class KeywordDetectorHook(BaseHook):
    """
    Detects keywords in messages and activates modes.
    
    Detects: ultrawork, search, analyze, and other mode triggers.
    """

    KEYWORDS = {
        "ultrawork": ["ultrawork", "ulw", "parallel", "run in parallel"],
        "search": ["search", "find", "grep"],
        "analyze": ["analyze", "investigate", "debug this"],
        "plan": ["plan", "let's plan", "create a plan"],
        "review": ["review", "code review", "check code"],
        "ralph": ["ralph", "don't stop", "keep going", "finish this"],
        "deep": ["deep", "thorough", "comprehensive"],
    }

    def __init__(self):
        super().__init__(
            name="keyword_detector",
            events=[HookEvent.MESSAGE_RECEIVED, HookEvent.MESSAGE_TRANSFORM]
        )

    async def execute(self, context: HookContext) -> HookResult:
        """Detect keywords in message."""
        if not context.message:
            return HookResult()

        message_lower = context.message.lower()
        detected: list[str] = []

        for mode, keywords in self.KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    detected.append(mode)
                    break

        if detected:
            context.set("detected_keywords", detected)
            context.set("primary_keyword", detected[0])
            self.logger.info(f"Detected keywords: {detected}")

        return HookResult(
            handled=len(detected) > 0,
            metadata={
                "keywords_found": detected,
                "count": len(detected)
            }
        )


class RalphLoopHook(BaseHook):
    """
    Ralph self-referential loop hook.
    
    Manages the ralph loop that continues until completion.
    """

    def __init__(self):
        super().__init__(
            name="ralph_loop",
            events=[
                HookEvent.SESSION_IDLE,
                HookEvent.MESSAGE_RECEIVED,
                HookEvent.TOOL_AFTER,
            ]
        )
        self.loop_active = False
        self.max_iterations = 100
        self.current_iteration = 0
        self.completion_marker = "<promise>DONE</promise>"

    async def execute(self, context: HookContext) -> HookResult:
        """Handle ralph loop logic."""
        if not self.loop_active:
            return HookResult()

        if context.event == HookEvent.MESSAGE_RECEIVED:
            message = context.message or ""
            if self.completion_marker in message:
                self.loop_active = False
                context.set("ralph_complete", True)
                return HookResult(handled=True, metadata={"completed": True})

        if context.event == HookEvent.SESSION_IDLE and self.loop_active:
            self.current_iteration += 1
            
            if self.current_iteration >= self.max_iterations:
                self.loop_active = False
                context.set("ralph_max_iterations", True)
                return HookResult(
                    handled=True,
                    metadata={
                        "max_reached": True,
                        "iterations": self.current_iteration
                    }
                )
                
            context.set("ralph_continue", True)
            return HookResult(handled=True, metadata={"continue": True})

        return HookResult()

    def start_loop(self, max_iterations: int = 100) -> None:
        """Start the ralph loop."""
        self.loop_active = True
        self.max_iterations = max_iterations
        self.current_iteration = 0
        self.logger.info(f"Ralph loop started (max: {max_iterations})")

    def stop_loop(self) -> None:
        """Stop the ralph loop."""
        self.loop_active = False
        self.logger.info(f"Ralph loop stopped at iteration {self.current_iteration}")

    @property
    def is_active(self) -> bool:
        """Check if loop is active."""
        return self.loop_active


class ContextInjectorHook(BaseHook):
    """
    Context injection hook.
    
    Auto-injects AGENTS.md, README.md, and rules when reading files.
    """

    def __init__(self):
        super().__init__(
            name="context_injector",
            events=[HookEvent.TOOL_BEFORE, HookEvent.CONTEXT_INJECT]
        )
        self.inject_agents_md = True
        self.inject_readme = True
        self.inject_rules = True

    async def execute(self, context: HookContext) -> HookResult:
        """Inject context before tool execution."""
        if context.tool_name not in ["Read", "Grep", "Glob"]:
            return HookResult()

        injected_content: list[str] = []

        if self.inject_agents_md:
            agents_md = await self.find_agents_md(context)
            if agents_md:
                injected_content.append(agents_md)

        if self.inject_readme:
            readme = await self.find_readme(context)
            if readme:
                injected_content.append(readme)

        if injected_content:
            context.set("injected_context", injected_content)
            return HookResult(
                modified=True,
                modified_content="\n\n".join(injected_content),
                metadata={"injected_files": len(injected_content)}
            )

        return HookResult()

    async def find_agents_md(self, context: HookContext) -> str | None:
        """Find AGENTS.md files in the path hierarchy."""
        return None

    async def find_readme(self, context: HookContext) -> str | None:
        """Find README.md in the path."""
        return None


class SessionRecoveryHook(BaseHook):
    """
    Session recovery hook.
    
    Recovers from common session errors.
    """

    def __init__(self):
        super().__init__(
            name="session_recovery",
            events=[HookEvent.SESSION_ERROR, HookEvent.TOOL_ERROR]
        )

    async def execute(self, context: HookContext) -> HookResult:
        """Attempt to recover from error."""
        error_msg = context.get("error", "")
        
        recovery_strategies = {
            "context_window": "compact_context",
            "rate_limit": "wait_and_retry",
            "timeout": "increase_timeout",
            "tool_not_found": "skip_tool",
            "parse_error": "fix_json",
        }

        for error_type, strategy in recovery_strategies.items():
            if error_type in error_msg.lower():
                context.set("recovery_strategy", strategy)
                context.set("recovery_needed", True)
                self.logger.info(f"Recovery strategy for {error_type}: {strategy}")
                return HookResult(
                    handled=True,
                    metadata={
                        "error_type": error_type,
                        "strategy": strategy
                    }
                )

        return HookResult()


class CommentCheckerHook(BaseHook):
    """
    Comment checker hook.
    
    Detects AI slop in comments and suggests improvements.
    """

    def __init__(self):
        super().__init__(
            name="comment_checker",
            events=[HookEvent.TOOL_AFTER]
        )
        self.slop_patterns = [
            r"^#\s*TODO:?\s*$",
            r"^#\s*FIXME:?\s*$",
            r"^#\s*XXX:?\s*$",
            r"# This (file|function|class) .+ does .+",
            r"# Used for .+ purposes?",
        ]
        self.slop_regex = [re.compile(p, re.IGNORECASE) for p in self.slop_patterns]

    async def execute(self, context: HookContext) -> HookResult:
        """Check output for AI slop comments."""
        if context.tool_name != "Read":
            return HookResult()

        output = context.tool_output
        if not isinstance(output, str):
            return HookResult()

        slop_found: list[dict[str, Any]] = []
        
        for i, line in enumerate(output.split("\n")):
            for pattern in self.slop_regex:
                if pattern.search(line):
                    slop_found.append({
                        "line": i + 1,
                        "content": line.strip(),
                        "pattern": pattern.pattern
                    })

        if slop_found:
            context.set("slop_comments", slop_found)
            return HookResult(
                handled=True,
                metadata={
                    "slop_count": len(slop_found),
                    "warning": "AI slop comments detected"
                }
            )

        return HookResult()
