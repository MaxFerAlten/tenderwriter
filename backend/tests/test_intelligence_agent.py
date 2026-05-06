"""Unit tests for the TenderIntelligenceAgent (PR-04)."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import AsyncMock

from test_module_loaders import load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


_AGENT_MODULE = load_service_test_module("app.intelligence.agent")
_PROMPTS = load_service_test_module("app.intelligence.prompts")
_REGISTRY_MODULE = load_service_test_module("app.intelligence.tool_registry")
_RESULT_MODELS = load_service_test_module("app.intelligence.result_models")

TenderIntelligenceAgent = _AGENT_MODULE.TenderIntelligenceAgent
classify_intent = _AGENT_MODULE.classify_intent
select_tools = _AGENT_MODULE.select_tools
TenderToolRegistry = _REGISTRY_MODULE.TenderToolRegistry
MAX_TOOLS_PER_QUERY = _PROMPTS.MAX_TOOLS_PER_QUERY


class _RecordingTool:
    """Stub tool that captures invocations and returns a fixed payload."""

    def __init__(self, name: str, payload: dict[str, Any]) -> None:
        self.name = name
        self.description = f"recording stub for {name}"
        self.input_keys = ("tender_id", "only_high_priority")
        self.calls: list[dict[str, Any]] = []
        self._payload = payload

    async def run(self, db, inputs):  # noqa: ANN001 - test stub
        self.calls.append({"db": db, "inputs": dict(inputs)})
        return dict(self._payload)


class _WriteTrappingSession:
    """Fake AsyncSession that fails the test if any write API is invoked."""

    def __init__(self) -> None:
        self.add = AsyncMock(side_effect=AssertionError("agent must not call add"))
        self.add_all = AsyncMock(side_effect=AssertionError("agent must not call add_all"))
        self.commit = AsyncMock(side_effect=AssertionError("agent must not commit"))
        self.flush = AsyncMock(side_effect=AssertionError("agent must not flush"))
        self.delete = AsyncMock(side_effect=AssertionError("agent must not delete"))


def _build_registry(panorama_payload=None, coverage_payload=None, evidence_payload=None):
    registry = TenderToolRegistry()
    registry.register(
        _RecordingTool(
            "coverage_analyzer",
            coverage_payload
            or {
                "tender_id": 1,
                "summary": {
                    "total_requirements": 10,
                    "fully_covered": 4,
                    "partially_covered": 2,
                    "uncovered": 4,
                    "high_priority_uncovered": 2,
                },
                "by_domain": [],
                "gaps": [
                    {
                        "requirement_id": 11,
                        "summary": "Certificazione ISO 27001 mancante",
                        "priority": "high",
                        "ontology_domain": "compliance",
                        "ontology_subdomain": "certification",
                        "mapped_section_id": None,
                        "mapped_section_title": None,
                        "coverage_status": "uncovered",
                        "coverage_source": "consolidated",
                    },
                    {
                        "requirement_id": 12,
                        "summary": "SLA di intervento entro 4 ore",
                        "priority": "medium",
                        "ontology_domain": "tecnico",
                        "ontology_subdomain": "sla",
                        "mapped_section_id": 5,
                        "mapped_section_title": "Servizi",
                        "coverage_status": "partially_covered",
                        "coverage_source": "consolidated",
                    },
                ],
            },
        )
    )
    registry.register(
        _RecordingTool(
            "evidence_auditor",
            evidence_payload
            or {
                "tender_id": 1,
                "only_high_priority": False,
                "summary": {
                    "requirements_checked": 8,
                    "strong_evidence": 3,
                    "weak_evidence": 3,
                    "missing_evidence": 2,
                },
                "findings": [
                    {
                        "requirement_id": 21,
                        "summary": "Curriculum tecnico responsabile progetto",
                        "priority": "high",
                        "evidence_status": "missing",
                        "expected_evidence_type": "documento",
                        "owner_role": "PM",
                        "ontology_domain": "tecnico",
                        "ontology_subdomain": "team",
                        "mapped_section_id": None,
                        "mapped_section_title": None,
                        "has_citation_metadata": False,
                    }
                ],
            },
        )
    )
    registry.register(
        _RecordingTool(
            "compliance_panorama",
            panorama_payload
            or {
                "tender_id": 1,
                "health": "amber",
                "analytical_phase": "S5",
                "auto_gate_status": "open",
                "summary": {
                    "failed_gates": 0,
                    "open_gates": 1,
                    "blocking_reworks": 0,
                    "unresolved_requirements": 6,
                    "high_priority_unresolved": 2,
                },
                "top_risks": [
                    {
                        "code": "unresolved_high_priority_requirements",
                        "severity": "medium",
                        "summary": "2 requisiti high-priority senza copertura.",
                    }
                ],
                "kpi_snapshot_delivered": True,
            },
        )
    )
    return registry


class IntentClassificationTests(unittest.TestCase):
    def test_amber_question_classifies_as_panorama(self) -> None:
        self.assertEqual(classify_intent("Why is this tender amber?"), "panorama")

    def test_italian_coverage_question(self) -> None:
        self.assertEqual(
            classify_intent("Quali requisiti restano scoperti?"),
            "coverage",
        )

    def test_evidence_keyword_matches_evidence(self) -> None:
        self.assertEqual(
            classify_intent("Mostrami le evidenze deboli"),
            "evidence",
        )

    def test_diagnostic_priority_over_panorama(self) -> None:
        self.assertEqual(
            classify_intent("Spiega perché lo stato è amber, deep dive"),
            "diagnostic",
        )

    def test_empty_question_falls_back_to_unknown(self) -> None:
        self.assertEqual(classify_intent(""), "unknown")
        self.assertEqual(classify_intent("ciao"), "unknown")


class ToolSelectionTests(unittest.TestCase):
    def test_panorama_intent_picks_panorama_first(self) -> None:
        registry = _build_registry()
        tools = select_tools("panorama", registry)
        self.assertEqual(tools[0], "compliance_panorama")
        self.assertLessEqual(len(tools), MAX_TOOLS_PER_QUERY)

    def test_selection_never_exceeds_cap(self) -> None:
        registry = _build_registry()
        for intent in ("coverage", "evidence", "panorama", "diagnostic", "unknown"):
            tools = select_tools(intent, registry)  # type: ignore[arg-type]
            self.assertLessEqual(len(tools), MAX_TOOLS_PER_QUERY)
            self.assertEqual(len(tools), len(set(tools)))

    def test_selection_skips_unregistered_tools(self) -> None:
        registry = TenderToolRegistry()
        registry.register(
            _RecordingTool("compliance_panorama", {"tender_id": 1, "summary": {}, "top_risks": []})
        )
        tools = select_tools("coverage", registry)
        self.assertNotIn("coverage_analyzer", tools)
        self.assertIn("compliance_panorama", tools)


class AgentQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_why_amber_happy_path(self) -> None:
        registry = _build_registry()
        agent = TenderIntelligenceAgent(registry)
        session = _WriteTrappingSession()

        result = await agent.query(
            db=session,
            tender_id=1,
            question="Why is this tender amber?",
            only_high_priority=False,
        )

        self.assertEqual(result.intent, "panorama")
        self.assertEqual(result.tools_used[0], "compliance_panorama")
        self.assertLessEqual(len(result.tools_used), MAX_TOOLS_PER_QUERY)
        self.assertIn("amber", result.answer.casefold())
        self.assertGreater(len(result.findings), 0)
        self.assertGreater(len(result.recommended_actions), 0)
        # all tools called with the same tender_id
        for tool_name in result.tools_used:
            tool = registry.get(tool_name)
            self.assertEqual(tool.calls[0]["inputs"]["tender_id"], 1)

    async def test_query_propagates_only_high_priority_flag(self) -> None:
        registry = _build_registry()
        agent = TenderIntelligenceAgent(registry)
        session = _WriteTrappingSession()

        await agent.query(
            db=session,
            tender_id=7,
            question="lacune probatorie",
            only_high_priority=True,
        )

        evidence_tool = registry.get("evidence_auditor")
        self.assertEqual(evidence_tool.calls[0]["inputs"]["only_high_priority"], True)

    async def test_agent_never_writes_to_session(self) -> None:
        registry = _build_registry()
        agent = TenderIntelligenceAgent(registry)
        session = _WriteTrappingSession()

        await agent.query(
            db=session,
            tender_id=1,
            question="why amber",
            only_high_priority=False,
        )

        session.add.assert_not_called()
        session.add_all.assert_not_called()
        session.commit.assert_not_called()
        session.flush.assert_not_called()
        session.delete.assert_not_called()

    async def test_tool_failure_is_isolated(self) -> None:
        registry = _build_registry()

        class _Boom:
            name = "compliance_panorama"
            description = "boom"
            input_keys = ("tender_id",)

            async def run(self, db, inputs):  # noqa: ANN001 - test stub
                raise RuntimeError("boom")

        # replace the panorama tool with a failing one
        registry._tools["compliance_panorama"] = _Boom()
        agent = TenderIntelligenceAgent(registry)
        session = _WriteTrappingSession()

        result = await agent.query(
            db=session,
            tender_id=1,
            question="why amber",
            only_high_priority=False,
        )

        self.assertIn("compliance_panorama", result.raw_tool_outputs)
        self.assertEqual(
            result.raw_tool_outputs["compliance_panorama"].get("error"),
            "tool_failed",
        )

    async def test_diagnostic_intent_runs_all_three_tools(self) -> None:
        registry = _build_registry()
        agent = TenderIntelligenceAgent(registry)
        session = _WriteTrappingSession()

        result = await agent.query(
            db=session,
            tender_id=1,
            question="Spiega perché siamo in stato amber, deep dive",
            only_high_priority=False,
        )

        self.assertEqual(result.intent, "diagnostic")
        self.assertEqual(len(result.tools_used), 3)
        self.assertEqual(
            set(result.tools_used), {"compliance_panorama", "coverage_analyzer", "evidence_auditor"}
        )


if __name__ == "__main__":
    unittest.main()
