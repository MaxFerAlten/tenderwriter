"""Unit tests for the Wave-2 intelligence tools (graph + contradiction)."""

from __future__ import annotations

import os
import unittest
from typing import Any

from test_module_loaders import load_models_test_module, load_service_test_module

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


_MODELS = load_models_test_module()
_GRAPH_MODULE = load_service_test_module("app.intelligence.tools.graph_path_explainer")
_CONTRADICTION_MODULE = load_service_test_module("app.intelligence.tools.contradiction_finder")
_TOOLS_PACKAGE = load_service_test_module("app.intelligence.tools")

GraphPathExplainer = _GRAPH_MODULE.GraphPathExplainer
ContradictionFinder = _CONTRADICTION_MODULE.ContradictionFinder
build_default_tool_registry = _TOOLS_PACKAGE.build_default_tool_registry

ComplianceGate = _MODELS.ComplianceGate
ComplianceGateStatus = _MODELS.ComplianceGateStatus
ComplianceStatus = _MODELS.ComplianceStatus
ConsolidatedRequirement = _MODELS.ConsolidatedRequirement
ContributionUnit = _MODELS.ContributionUnit
ContributionUnitStatus = _MODELS.ContributionUnitStatus
Proposal = _MODELS.Proposal
ProposalSection = _MODELS.ProposalSection
ReviewCycle = _MODELS.ReviewCycle
ReviewCycleStatus = _MODELS.ReviewCycleStatus
ReworkAction = _MODELS.ReworkAction
ReworkStatus = _MODELS.ReworkStatus
SectionStatus = _MODELS.SectionStatus
Tender = _MODELS.Tender
TenderRequirement = _MODELS.TenderRequirement


class _FakeExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> _FakeExecuteResult:
        return self

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _RoutingSession:
    """Async session fake that routes statements based on FROM-table keywords.

    Each handler returns either a list of rows or ``None`` to indicate that the
    statement is not handled. The first handler that returns a non-``None``
    value wins.
    """

    def __init__(self, *, handlers: list) -> None:
        self._handlers = handlers
        self.statements: list[str] = []

    async def execute(self, statement):
        compiled = str(statement).lower()
        self.statements.append(compiled)
        for handler in self._handlers:
            rows = handler(compiled)
            if rows is not None:
                return _FakeExecuteResult(rows)
        return _FakeExecuteResult([])


def _make_consolidated(
    *,
    id_: int,
    text: str,
    metadata: dict[str, Any] | None = None,
    tender_id: int = 50,
) -> ConsolidatedRequirement:
    cr = ConsolidatedRequirement(
        id=id_,
        tender_id=tender_id,
        canonical_text=text,
        metadata_json=dict(metadata or {}),
    )
    return cr


def _build_full_tender_for_contradictions() -> Tender:
    """Tender exercising the three contradiction kinds."""

    tender = Tender(id=50, title="Wave2 contradiction tender")

    section_rejected = ProposalSection(
        id=901,
        proposal_id=801,
        title="Compliance",
        status=SectionStatus.IN_PROGRESS,
    )
    section_approved = ProposalSection(
        id=902,
        proposal_id=801,
        title="Technical",
        status=SectionStatus.APPROVED,
    )
    proposal = Proposal(id=801, tender_id=50, title="Master proposal")
    proposal.sections = [section_rejected, section_approved]

    high_priority_req = TenderRequirement(
        id=2001,
        tender_id=50,
        requirement_text="Possedere certificazione ISO 27001 obbligatoria.",
        category="compliance",
        priority="high",
        proposal_section_id=901,
    )
    high_priority_req.proposal_section = section_rejected

    tender.requirements = [high_priority_req]
    tender.proposals = [proposal]

    consolidated_no_evidence = _make_consolidated(
        id_=3001,
        text="Il fornitore deve fornire SLA del 99,9%.",
        metadata={"proposal_section_id": 902, "sources": [{"raw_candidate": {}}]},
    )
    # Modal contradiction: same topic signature ("applicata cifratura forte"),
    # one with a positive marker and one with a non-overlapping negative marker.
    consolidated_positive = _make_consolidated(
        id_=3010,
        text="Cifratura forte applicata obbligatorio sui messaggi.",
    )
    consolidated_negative = _make_consolidated(
        id_=3011,
        text="Cifratura forte applicata vietato sui messaggi.",
    )

    tender.consolidated_requirements = [
        consolidated_no_evidence,
        consolidated_positive,
        consolidated_negative,
    ]
    return tender


class ContradictionFinderTests(unittest.IsolatedAsyncioTestCase):
    async def test_emits_three_contradiction_kinds(self) -> None:
        tender = _build_full_tender_for_contradictions()
        contribution = ContributionUnit(
            id=400,
            tender_id=50,
            proposal_section_id=901,
            title="Compliance contribution",
            status=ContributionUnitStatus.BLOCKED,
        )
        rework = ReworkAction(
            id=500,
            contribution_unit_id=400,
            severity="high",
            is_blocking=True,
            status=ReworkStatus.OPEN,
        )
        gate = ComplianceGate(
            id=600,
            tender_id=50,
            contribution_unit_id=400,
            gate_name="Legal sign-off",
            status=ComplianceGateStatus.FAILED,
        )

        def handler_tender(sql: str):
            if "from tenders" in sql:
                return [tender]
            return None

        def handler_contributions(sql: str):
            if "from contribution_units" in sql and "rework_actions" not in sql:
                return [contribution]
            return None

        def handler_reworks(sql: str):
            if (
                "from rework_actions" in sql
                or "rework_actions" in sql
                and "join contribution_units" in sql
            ):
                return [rework]
            return None

        def handler_gates(sql: str):
            if "from compliance_gates" in sql:
                return [gate]
            return None

        session = _RoutingSession(
            handlers=[handler_tender, handler_contributions, handler_reworks, handler_gates]
        )
        tool = ContradictionFinder()

        result = await tool.run(session, {"tender_id": 50})

        self.assertEqual(result["tender_id"], 50)
        kinds = {finding["kind"] for finding in result["findings"]}
        self.assertIn("requirement_vs_proposal", kinds)
        self.assertIn("proposal_vs_evidence", kinds)
        self.assertIn("requirement_vs_requirement", kinds)
        summary = result["summary"]
        self.assertEqual(
            summary["total"],
            sum(
                summary[k]
                for k in (
                    "requirement_vs_proposal",
                    "proposal_vs_evidence",
                    "requirement_vs_requirement",
                )
            ),
        )
        self.assertGreaterEqual(summary["requirement_vs_proposal"], 1)
        self.assertGreaterEqual(summary["proposal_vs_evidence"], 1)
        self.assertGreaterEqual(summary["requirement_vs_requirement"], 1)

    async def test_returns_empty_when_tender_missing(self) -> None:
        def handler_tender(sql: str):
            if "from tenders" in sql:
                return []
            return None

        session = _RoutingSession(handlers=[handler_tender])
        tool = ContradictionFinder()
        result = await tool.run(session, {"tender_id": 999})
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(result["findings"], [])

    async def test_rejects_missing_tender_id(self) -> None:
        tool = ContradictionFinder()
        with self.assertRaises(ValueError):
            await tool.run(_RoutingSession(handlers=[]), {})


class GraphPathExplainerTests(unittest.IsolatedAsyncioTestCase):
    async def test_assembles_full_chain(self) -> None:
        section = ProposalSection(
            id=701,
            proposal_id=601,
            title="Technical plan",
            status=SectionStatus.IN_PROGRESS,
        )
        requirement = TenderRequirement(
            id=1001,
            tender_id=42,
            requirement_text="Garantire SLA 99,9%.",
            priority="high",
            proposal_section_id=701,
            compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
        )
        contribution = ContributionUnit(
            id=801,
            tender_id=42,
            proposal_section_id=701,
            title="SLA contribution",
            status=ContributionUnitStatus.IN_REVIEW,
            department_name="Operations",
        )
        review = ReviewCycle(
            id=901,
            contribution_unit_id=801,
            stage_name="legal-review",
            status=ReviewCycleStatus.OPEN,
            outcome=None,
        )
        rework = ReworkAction(
            id=1101,
            contribution_unit_id=801,
            reason="Citazione mancante per SLA",
            severity="medium",
            is_blocking=False,
            status=ReworkStatus.OPEN,
        )
        gate = ComplianceGate(
            id=1201,
            tender_id=42,
            contribution_unit_id=801,
            gate_name="Operational sign-off",
            status=ComplianceGateStatus.OPEN,
        )

        def handler_requirement(sql: str):
            if "from tender_requirements" in sql:
                return [requirement]
            if "from consolidated_requirements" in sql:
                return []
            return None

        def handler_section(sql: str):
            if "from proposal_sections" in sql:
                return [section]
            return None

        def handler_contributions(sql: str):
            if "from contribution_units" in sql:
                return [contribution]
            return None

        def handler_reviews(sql: str):
            if "from review_cycles" in sql:
                return [review]
            return None

        def handler_reworks(sql: str):
            if "from rework_actions" in sql:
                return [rework]
            return None

        def handler_gates(sql: str):
            if "from compliance_gates" in sql:
                return [gate]
            return None

        session = _RoutingSession(
            handlers=[
                handler_requirement,
                handler_section,
                handler_contributions,
                handler_reviews,
                handler_reworks,
                handler_gates,
            ]
        )
        tool = GraphPathExplainer()
        result = await tool.run(session, {"tender_id": 42, "requirement_id": 1001})

        self.assertTrue(result["found"])
        kinds = [step["kind"] for step in result["path"]]
        self.assertEqual(
            kinds,
            ["requirement", "section", "contribution", "review", "rework", "gate"],
        )
        self.assertIn("Requirement #1001", result["narrative"])
        self.assertIn("Section #701", result["narrative"])
        self.assertIn("Contribution #801", result["narrative"])
        self.assertIn("Gate #1201", result["narrative"])

    async def test_returns_not_found_when_requirement_missing(self) -> None:
        def handler_empty(_sql: str):
            return []

        session = _RoutingSession(handlers=[handler_empty])
        tool = GraphPathExplainer()
        result = await tool.run(session, {"tender_id": 1, "requirement_id": 999})
        self.assertFalse(result["found"])
        self.assertEqual(result["path"], [])
        self.assertIn("Nessun requisito", result["narrative"])

    async def test_rejects_missing_inputs(self) -> None:
        tool = GraphPathExplainer()
        with self.assertRaises(ValueError):
            await tool.run(_RoutingSession(handlers=[]), {"tender_id": 1})
        with self.assertRaises(ValueError):
            await tool.run(_RoutingSession(handlers=[]), {"requirement_id": 1})


class DefaultRegistryWithWave2Tests(unittest.IsolatedAsyncioTestCase):
    def test_default_registry_includes_wave2_tools(self) -> None:
        registry = build_default_tool_registry()
        names = {descriptor.name for descriptor in registry.list_tools()}
        self.assertEqual(
            names,
            {
                "compliance_panorama",
                "contradiction_finder",
                "coverage_analyzer",
                "evidence_auditor",
                "graph_path_explainer",
            },
        )


if __name__ == "__main__":
    unittest.main()
