"""Keyword detection system for automatic workflow activation."""

from dataclasses import dataclass
from typing import Callable
import re


@dataclass
class KeywordMapping:
    keywords: list[str]
    action: str
    description: str
    skill: str | None = None


class KeywordDetector:
    """Detects keywords in user messages and triggers appropriate actions."""

    MAPPINGS: list[KeywordMapping] = [
        KeywordMapping(
            keywords=["ralph", "don't stop", "must complete", "keep going", "finish this"],
            action="ralph",
            description="Start autonomous execution loop",
            skill="ralph"
        ),
        KeywordMapping(
            keywords=["team", "swarm", "coordinated team", "parallel agents"],
            action="team",
            description="Start team coordination",
            skill="team"
        ),
        KeywordMapping(
            keywords=["analyze", "investigate", "debug this"],
            action="analyze",
            description="Run deep analysis",
            skill=None
        ),
        KeywordMapping(
            keywords=["plan this", "plan the", "let's plan", "create a plan"],
            action="plan",
            description="Start planning workflow",
            skill=None
        ),
        KeywordMapping(
            keywords=["ultrawork", "ulw", "parallel", "run in parallel"],
            action="ultrawork",
            description="Run tasks in parallel",
            skill=None
        ),
        KeywordMapping(
            keywords=["ultraqa", "qa", "quality assurance", "test everything"],
            action="ultraqa",
            description="Run QA cycling",
            skill=None
        ),
        KeywordMapping(
            keywords=["tdd", "test first", "test-driven"],
            action="tdd",
            description="Start TDD workflow",
            skill=None
        ),
        KeywordMapping(
            keywords=["code review", "review code", "review my code"],
            action="code-review",
            description="Run code review",
            skill=None
        ),
        KeywordMapping(
            keywords=["security review", "security audit", "check for vulnerabilities"],
            action="security-review",
            description="Run security audit",
            skill=None
        ),
        KeywordMapping(
            keywords=["cancel", "stop", "abort", "quit"],
            action="cancel",
            description="Cancel current workflow",
            skill=None
        ),
        KeywordMapping(
            keywords=["fix build", "type errors", "build failed"],
            action="build-fix",
            description="Fix build errors",
            skill=None
        ),
        KeywordMapping(
            keywords=["web-clone", "clone site", "clone website", "clone webpage"],
            action="web-clone",
            description="Clone a website",
            skill=None
        ),
        KeywordMapping(
            keywords=["autopilot", "auto pilot", "autonomous", "build me", "create me", "make me", "full auto", "handle it all", "i want a"],
            action="autopilot",
            description="Full autonomous end-to-end execution",
            skill="autopilot"
        ),
        KeywordMapping(
            keywords=["deep interview", "interview me", "ask me everything", "don't assume", "ouroboros", "clarify requirements"],
            action="deep-interview",
            description="Socratic requirements clarification",
            skill="deep-interview"
        ),
        KeywordMapping(
            keywords=["doctor", "diagnose", "fix installation", "check health", "troubleshooting"],
            action="doctor",
            description="Diagnose and fix issues",
            skill="doctor"
        ),
        KeywordMapping(
            keywords=["git master", "git expert", "atomic commit", "interactive rebase", "squash commits"],
            action="git-master",
            description="Git expert operations",
            skill="git-master"
        ),
        KeywordMapping(
            keywords=["visual verdict", "visual check", "screenshot comparison", "compare screenshots", "visual diff"],
            action="visual-verdict",
            description="Visual QA comparison",
            skill="visual-verdict"
        ),
        KeywordMapping(
            keywords=["ecomode", "eco", "save tokens", "cost efficient", "cheap mode"],
            action="ecomode",
            description="Token-efficient routing",
            skill="ecomode"
        ),
        KeywordMapping(
            keywords=["deepsearch", "deep search", "thorough search", "find all", "search everywhere"],
            action="deepsearch",
            description="Thorough codebase search",
            skill="deepsearch"
        ),
        KeywordMapping(
            keywords=["swarm", "swarming", "coordinated agents", "multi-agent"],
            action="swarm",
            description="Swarm coordination (alias for team)",
            skill="swarm"
        ),
        KeywordMapping(
            keywords=["trace", "show trace", "flow trace", "timeline", "event log"],
            action="trace",
            description="Show execution trace",
            skill="trace"
        ),
    ]

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, action: str, handler: Callable):
        """Register a handler for an action."""
        self._handlers[action] = handler

    def detect(self, text: str) -> list[KeywordMapping]:
        """Detect keywords in text. Returns list of matching mappings."""
        text_lower = text.lower()
        matches = []

        for mapping in self.MAPPINGS:
            for keyword in mapping.keywords:
                if keyword.lower() in text_lower:
                    matches.append(mapping)
                    break

        return matches

    def get_triggered_action(self, text: str) -> KeywordMapping | None:
        """Get the most specific triggered action."""
        matches = self.detect(text)
        if not matches:
            return None

        return max(matches, key=lambda m: max(len(k) for k in m.keywords))

    def extract_task(self, text: str, mapping: KeywordMapping) -> str:
        """Extract the actual task from text after removing triggered keywords."""
        result = text
        for keyword in mapping.keywords:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            result = pattern.sub("", result)

        return result.strip()

    def execute_triggered(self, text: str) -> tuple[str | None, str]:
        """Detect and execute triggered action. Returns (action, extracted_task)."""
        mapping = self.get_triggered_action(text)
        if not mapping:
            return None, text

        handler = self._handlers.get(mapping.action)
        if handler:
            task = self.extract_task(text, mapping)
            handler(task)
            return mapping.action, task

        return mapping.action, self.extract_task(text, mapping)


keyword_detector = KeywordDetector()
