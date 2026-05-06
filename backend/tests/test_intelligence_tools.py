"""Unit tests for the Wave-1 intelligence tools + registry."""

from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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
_TOOL_REGISTRY_MODULE = load_service_test_module("app.intelligence.tool_registry")
_COVERAGE_MODULE = load_service_test_module("app.intelligence.tools.coverage_analyzer")
_EVIDENCE_MODULE = load_service_test_module("app.intelligence.tools.evidence_auditor")
_PANORAMA_MODULE = load_service_test_module("app.intelligence.tools.compliance_panorama")
_TOOLS_PACKAGE = load_service_test_module("app.intelligence.tools")

TenderToolRegistry = _TOOL_REGISTRY_MODULE.TenderToolRegistry
ToolDescriptor = _TOOL_REGISTRY_MODULE.ToolDescriptor
CoverageAnalyzer = _COVERAGE_MODULE.CoverageAnalyzer
EvidenceAuditor = _EVIDENCE_MODULE.EvidenceAuditor
CompliancePanorama = _PANORAMA_MODULE.CompliancePanorama
build_default_tool_registry = _TOOLS_PACKAGE.build_default_tool_registry

ComplianceGate = _MODELS.ComplianceGate
ComplianceGateStatus = _MODELS.ComplianceGateStatus
ComplianceStatus = _MODELS.ComplianceStatus
ConsolidatedRequirement = _MODELS.ConsolidatedRequirement
ContributionUnit = _MODELS.ContributionUnit
Proposal = _MODELS.Proposal
ProposalSection = _MODELS.ProposalSection
ReworkAction = _MODELS.ReworkAction
ReworkStatus = _MODELS.ReworkStatus
SectionStatus = _MODELS.SectionStatus
Tender = _MODELS.Tender
TenderRequirement = _MODELS.TenderRequirement


@dataclass
class _QueryResponse:
    rows: list[Any]


class _FakeExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeExecuteResult:
        return self

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeAsyncSession:
    """Dispatches query responses based on the SQL text prefix."""

    def __init__(
        self,
        *,
        tender: Tender | None,
        gates: list[ComplianceGate] | None = None,
        reworks: list[ReworkAction] | None = None,
    ) -> None:
        self._tender = tender
        self._gates = list(gates or [])
        self._reworks = list(reworks or [])
        self.statements: list[str] = []

    async def execute(self, statement):
        compiled = str(statement).lower()
        self.statements.append(compiled)
        if (
            "from tenders" in compiled
            or "tenders." in compiled
            and "tender_id" not in compiled.split("from")[1]
        ):
            return _FakeExecuteResult([self._tender] if self._tender is not None else [])
        if "compliance_gates" in compiled:
            return _FakeExecuteResult(self._gates)
        if "rework_actions" in compiled:
            return _FakeExecuteResult(self._reworks)
        return _FakeExecuteResult([])


class _FakeKpiClient:
    def __init__(self, snapshot: dict[str, Any] | Exception | None = None) -> None:
        self.snapshot = snapshot
        self.calls: list[str] = []

    async def get_tender_snapshot(self, external_tender_id: str):
        self.calls.append(external_tender_id)
        if isinstance(self.snapshot, Exception):
            raise self.snapshot
        if self.snapshot is None:
            return SimpleNamespace(
                delivered=False, response_json={}, status_code=None, error_message="no-kpi"
            )
        return SimpleNamespace(
            delivered=True,
            response_json=dict(self.snapshot),
            status_code=200,
            error_message=None,
        )


class _DummyTool:
    def __init__(self, name: str, description: str = "stub tool") -> None:
        self.name = name
        self.description = description
        self.input_keys = ("tender_id",)
        self.calls: list[dict[str, Any]] = []

    async def run(self, db, inputs):  # noqa: ANN001 (tests)
        self.calls.append(dict(inputs))
        return {"tool": self.name, "ok": True}


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    def test_register_rejects_duplicates(self) -> None:
        registry = TenderToolRegistry()
        registry.register(_DummyTool("alpha"))
        with self.assertRaises(ValueError):
            registry.register(_DummyTool("alpha"))

    def test_register_requires_name(self) -> None:
        registry = TenderToolRegistry()
        with self.assertRaises(ValueError):
            registry.register(SimpleNamespace(name="", description=""))

    def test_list_tools_returns_sorted_descriptors(self) -> None:
        registry = TenderToolRegistry()
        registry.register(_DummyTool("zulu"))
        registry.register(_DummyTool("alpha"))
        descriptors = registry.list_tools()
        self.assertEqual([d.name for d in descriptors], ["alpha", "zulu"])
        self.assertIsInstance(descriptors[0], ToolDescriptor)

    async def test_run_dispatches_to_registered_tool(self) -> None:
        registry = TenderToolRegistry()
        tool = _DummyTool("coverage_analyzer")
        registry.register(tool)
        result = await registry.run("coverage_analyzer", db=None, inputs={"tender_id": 42})
        self.assertEqual(result, {"tool": "coverage_analyzer", "ok": True})
        self.assertEqual(tool.calls, [{"tender_id": 42}])

    def test_default_registry_exposes_wave1_tools(self) -> None:
        registry = build_default_tool_registry()
        names = [d.name for d in registry.list_tools()]
        for required in ("compliance_panorama", "coverage_analyzer", "evidence_auditor"):
            self.assertIn(required, names)


def _tender_with_legacy_requirements() -> Tender:
    tender = Tender(id=91, title="Legacy tender")
    section_approved = ProposalSection(
        id=701,
        proposal_id=811,
        title="Compliance matrix",
        status=SectionStatus.APPROVED,
    )
    section_in_progress = ProposalSection(
        id=702,
        proposal_id=811,
        title="Technical plan",
        status=SectionStatus.IN_PROGRESS,
    )

    req_approved = TenderRequirement(
        id=1001,
        tender_id=91,
        requirement_text="Il concorrente deve possedere certificazione ISO 27001.",
        category="compliance",
        priority="high",
        compliance_status=ComplianceStatus.FULLY_ADDRESSED,
        proposal_section_id=701,
    )
    req_approved.proposal_section = section_approved

    req_in_progress = TenderRequirement(
        id=1002,
        tender_id=91,
        requirement_text="Il fornitore deve garantire SLA di disponibilità del 99,9%.",
        category="technical",
        priority="high",
        compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
        proposal_section_id=702,
    )
    req_in_progress.proposal_section = section_in_progress

    req_uncovered = TenderRequirement(
        id=1003,
        tender_id=91,
        requirement_text="Il fatturato minimo triennale deve essere di 2 milioni di euro.",
        category="economic",
        priority="medium",
        compliance_status=ComplianceStatus.NOT_ADDRESSED,
    )

    req_uncovered_high = TenderRequirement(
        id=1004,
        tender_id=91,
        requirement_text="Dichiarazione sostitutiva ex D.P.R. 445/2000 - modulo allegato.",
        category="administrative",
        priority="high",
        compliance_status=ComplianceStatus.NOT_ADDRESSED,
    )

    tender.requirements = [req_approved, req_in_progress, req_uncovered, req_uncovered_high]
    tender.consolidated_requirements = []
    proposal = Proposal(id=811, tender_id=91, title="Proposal")
    proposal.sections = [section_approved, section_in_progress]
    tender.proposals = [proposal]
    return tender


class CoverageAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_coverage_summary_counts_and_domain_groups(self) -> None:
        tender = _tender_with_legacy_requirements()
        db = _FakeAsyncSession(tender=tender)
        tool = CoverageAnalyzer()

        result = await tool.run(db, {"tender_id": 91})

        self.assertEqual(result["tender_id"], 91)
        summary = result["summary"]
        self.assertEqual(summary["total_requirements"], 4)
        self.assertEqual(summary["fully_covered"], 1)
        self.assertEqual(summary["partially_covered"], 1)
        self.assertEqual(summary["uncovered"], 2)
        self.assertEqual(summary["high_priority_uncovered"], 1)

        domains = {bucket["domain"]: bucket for bucket in result["by_domain"]}
        self.assertIn("compliance", domains)
        self.assertIn("tecnico", domains)
        self.assertIn("economico_finanziario", domains)
        self.assertEqual(domains["compliance"]["covered"], 1)
        self.assertEqual(domains["tecnico"]["partial"], 1)
        self.assertEqual(domains["economico_finanziario"]["uncovered"], 1)

        gap_ids = [gap["requirement_id"] for gap in result["gaps"]]
        self.assertIn(1002, gap_ids)
        self.assertIn(1003, gap_ids)
        self.assertIn(1004, gap_ids)
        self.assertNotIn(1001, gap_ids)
        self.assertEqual(result["gaps"][0]["priority"], "high")

    async def test_returns_empty_payload_when_tender_missing(self) -> None:
        db = _FakeAsyncSession(tender=None)
        tool = CoverageAnalyzer()
        result = await tool.run(db, {"tender_id": 777})
        self.assertEqual(result["summary"]["total_requirements"], 0)
        self.assertEqual(result["gaps"], [])

    async def test_rejects_missing_tender_id(self) -> None:
        tool = CoverageAnalyzer()
        with self.assertRaises(ValueError):
            await tool.run(_FakeAsyncSession(tender=None), {})


class EvidenceAuditorTests(unittest.IsolatedAsyncioTestCase):
    async def test_evidence_classification_strong_weak_missing(self) -> None:
        tender = _tender_with_legacy_requirements()
        db = _FakeAsyncSession(tender=tender)
        tool = EvidenceAuditor()

        result = await tool.run(db, {"tender_id": 91})

        summary = result["summary"]
        self.assertEqual(summary["requirements_checked"], 4)
        self.assertEqual(summary["strong_evidence"], 1)
        self.assertEqual(summary["weak_evidence"], 1)
        self.assertEqual(summary["missing_evidence"], 2)

        by_id = {finding["requirement_id"]: finding for finding in result["findings"]}
        self.assertEqual(by_id[1001]["evidence_status"], "strong")
        self.assertEqual(by_id[1002]["evidence_status"], "weak")
        self.assertEqual(by_id[1003]["evidence_status"], "missing")
        self.assertEqual(by_id[1004]["evidence_status"], "missing")

        self.assertEqual(by_id[1001]["ontology_domain"], "compliance")
        self.assertEqual(by_id[1002]["ontology_domain"], "tecnico")
        self.assertEqual(by_id[1003]["ontology_domain"], "economico_finanziario")

    async def test_only_high_priority_filters_findings(self) -> None:
        tender = _tender_with_legacy_requirements()
        db = _FakeAsyncSession(tender=tender)
        tool = EvidenceAuditor()

        result = await tool.run(db, {"tender_id": 91, "only_high_priority": True})
        priorities = {finding["priority"] for finding in result["findings"]}
        self.assertEqual(priorities, {"high"})
        self.assertEqual(result["summary"]["requirements_checked"], 3)


class CompliancePanoramaTests(unittest.IsolatedAsyncioTestCase):
    async def test_aggregates_gates_reworks_and_snapshot(self) -> None:
        tender = _tender_with_legacy_requirements()
        gates = [
            ComplianceGate(
                id=1,
                tender_id=91,
                gate_name="Auto compliance readiness",
                status=ComplianceGateStatus.OPEN,
            ),
            ComplianceGate(
                id=2,
                tender_id=91,
                gate_name="Legal sign-off",
                status=ComplianceGateStatus.FAILED,
            ),
        ]
        reworks = [
            ReworkAction(
                id=10,
                contribution_unit_id=200,
                severity="high",
                is_blocking=True,
                status=ReworkStatus.OPEN,
            ),
        ]
        db = _FakeAsyncSession(tender=tender, gates=gates, reworks=reworks)
        kpi = _FakeKpiClient(snapshot={"health": "amber", "analytical_phase": "S8"})
        tool = CompliancePanorama(kpi_client=kpi)

        result = await tool.run(db, {"tender_id": 91})

        self.assertEqual(result["tender_id"], 91)
        self.assertEqual(result["health"], "red")
        self.assertEqual(result["analytical_phase"], "S8")
        self.assertEqual(result["auto_gate_status"], "open")
        self.assertEqual(result["summary"]["failed_gates"], 1)
        self.assertEqual(result["summary"]["open_gates"], 1)
        self.assertEqual(result["summary"]["blocking_reworks"], 1)
        self.assertEqual(result["summary"]["unresolved_requirements"], 3)
        self.assertEqual(result["summary"]["high_priority_unresolved"], 2)
        self.assertTrue(result["kpi_snapshot_delivered"])
        codes = {risk["code"] for risk in result["top_risks"]}
        self.assertIn("failed_gate", codes)
        self.assertIn("blocking_rework", codes)
        self.assertIn("unresolved_high_priority_requirements", codes)
        self.assertEqual(kpi.calls, ["91"])

    async def test_falls_back_to_local_health_when_kpi_unavailable(self) -> None:
        tender = _tender_with_legacy_requirements()
        tender.requirements = [tender.requirements[0]]
        db = _FakeAsyncSession(tender=tender, gates=[], reworks=[])
        kpi = _FakeKpiClient(snapshot=None)
        tool = CompliancePanorama(kpi_client=kpi)

        result = await tool.run(db, {"tender_id": 91})

        self.assertFalse(result["kpi_snapshot_delivered"])
        self.assertEqual(result["health"], "green")
        self.assertEqual(result["top_risks"], [])

    async def test_swallows_kpi_exceptions(self) -> None:
        tender = _tender_with_legacy_requirements()
        db = _FakeAsyncSession(tender=tender, gates=[], reworks=[])
        kpi = _FakeKpiClient(snapshot=RuntimeError("kpi-down"))
        tool = CompliancePanorama(kpi_client=kpi)

        result = await tool.run(db, {"tender_id": 91})
        self.assertFalse(result["kpi_snapshot_delivered"])
        self.assertIsNone(result["analytical_phase"])

    async def test_read_only_does_not_touch_session(self) -> None:
        tender = _tender_with_legacy_requirements()
        db = _FakeAsyncSession(tender=tender, gates=[], reworks=[])
        db.add = AsyncMock()  # would blow up if called
        db.flush = AsyncMock()
        tool = CompliancePanorama(kpi_client=_FakeKpiClient(snapshot=None))

        await tool.run(db, {"tender_id": 91})

        db.add.assert_not_called()
        db.flush.assert_not_called()


if __name__ == "__main__":
    unittest.main()
