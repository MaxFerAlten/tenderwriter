"""Tests for the GraphLifecycleProjector (PR-06)."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

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
_PROJECTOR = load_service_test_module("app.intelligence.lifecycle_projector")

ComplianceStatus = _MODELS.ComplianceStatus
ContributionUnit = _MODELS.ContributionUnit
ContributionUnitStatus = _MODELS.ContributionUnitStatus
ProposalSection = _MODELS.ProposalSection
ReworkAction = _MODELS.ReworkAction
ReworkStatus = _MODELS.ReworkStatus
SectionStatus = _MODELS.SectionStatus
TenderRequirement = _MODELS.TenderRequirement
ComplianceGate = _MODELS.ComplianceGate
ComplianceGateStatus = _MODELS.ComplianceGateStatus

derive_snapshot_delta = _PROJECTOR.derive_snapshot_delta
project_requirement_event = _PROJECTOR.project_requirement_event
refresh_requirement_snapshot = _PROJECTOR.refresh_requirement_snapshot
explain_requirement_path = _PROJECTOR.explain_requirement_path
project_workflow_events = _PROJECTOR.project_workflow_events
requirement_node_id = _PROJECTOR.requirement_node_id
set_active_rag_engine = _PROJECTOR.set_active_rag_engine
get_active_rag_engine = _PROJECTOR.get_active_rag_engine


class _FakeGraphRetriever:
    def __init__(self) -> None:
        self.snapshots: list[tuple[str, dict]] = []
        self.events: list[tuple[str, dict]] = []
        self.lifecycle_payload: dict = {"snapshot": {}, "events": []}

    async def update_requirement_snapshot(self, requirement_id: str, snapshot: dict) -> None:
        self.snapshots.append((requirement_id, dict(snapshot)))

    async def append_requirement_lifecycle_event(self, requirement_id: str, event: dict) -> None:
        self.events.append((requirement_id, dict(event)))

    async def fetch_requirement_lifecycle(self, requirement_id: str, *, limit: int = 25) -> dict:
        return dict(self.lifecycle_payload)


class _FakeRagEngine:
    def __init__(self, *, graph: _FakeGraphRetriever | None = None) -> None:
        self.graph_retriever = graph or _FakeGraphRetriever()
        self.ensure_initialized = AsyncMock(return_value=None)


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


class SnapshotDeltaTests(unittest.TestCase):
    def test_review_approved_marks_fully_addressed(self) -> None:
        delta = derive_snapshot_delta("review_approved")
        self.assertEqual(delta["current_status"], "fully_addressed")
        self.assertEqual(delta["coverage_status"], "covered")
        self.assertEqual(delta["risk_level"], "green")

    def test_rework_requested_flips_amber(self) -> None:
        delta = derive_snapshot_delta("rework_requested")
        self.assertEqual(delta["risk_level"], "amber")
        self.assertEqual(delta["coverage_status"], "rework")

    def test_compliance_gate_failed_marks_red(self) -> None:
        delta = derive_snapshot_delta("compliance_gate_failed")
        self.assertEqual(delta["gate_state"], "failed")
        self.assertEqual(delta["risk_level"], "red")

    def test_unknown_event_returns_empty(self) -> None:
        self.assertEqual(derive_snapshot_delta("unknown_event"), {})


class RequirementNodeIdTests(unittest.TestCase):
    def test_canonical_format(self) -> None:
        self.assertEqual(
            requirement_node_id(42, 1001),
            "tender-42-requirement-1001",
        )


class ProjectRequirementEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_appends_event_and_updates_snapshot(self) -> None:
        graph = _FakeGraphRetriever()
        engine = _FakeRagEngine(graph=graph)
        result = await project_requirement_event(
            rag_engine=engine,
            tender_id=42,
            requirement_id=1001,
            event_type="review_approved",
            occurred_at=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
            external_event_id="evt-1",
            actor_id=7,
            payload={"external_review_cycle_id": "55"},
        )

        self.assertTrue(result.projected)
        self.assertTrue(result.snapshot_updated)
        self.assertEqual(result.requirement_node_id, "tender-42-requirement-1001")
        self.assertEqual(len(graph.events), 1)
        node_id, evt = graph.events[0]
        self.assertEqual(node_id, "tender-42-requirement-1001")
        self.assertEqual(evt["external_event_id"], "evt-1")
        self.assertEqual(evt["event_type"], "review_approved")
        self.assertEqual(evt["actor_id"], 7)
        self.assertEqual(len(graph.snapshots), 1)
        snap_id, snap = graph.snapshots[0]
        self.assertEqual(snap_id, "tender-42-requirement-1001")
        self.assertEqual(snap["current_status"], "fully_addressed")
        self.assertEqual(snap["last_event_type"], "review_approved")
        self.assertEqual(snap["last_event_at"], "2026-04-19T12:00:00+00:00")

    async def test_returns_error_when_engine_missing(self) -> None:
        result = await project_requirement_event(
            rag_engine=None,
            tender_id=1,
            requirement_id=2,
            event_type="rework_requested",
            occurred_at=None,
            external_event_id="evt-2",
        )
        self.assertFalse(result.projected)
        self.assertFalse(result.snapshot_updated)
        self.assertIn("graph retriever unavailable", result.error or "")

    async def test_unknown_event_still_appends_event_with_no_status_change(self) -> None:
        graph = _FakeGraphRetriever()
        engine = _FakeRagEngine(graph=graph)
        result = await project_requirement_event(
            rag_engine=engine,
            tender_id=42,
            requirement_id=1001,
            event_type="totally_unknown_event",
            occurred_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            external_event_id="evt-x",
        )
        self.assertTrue(result.projected)
        self.assertTrue(result.snapshot_updated)
        # Snapshot still records last_event_type/at even when delta is empty.
        _, snap = graph.snapshots[0]
        self.assertEqual(snap["last_event_type"], "totally_unknown_event")
        self.assertNotIn("current_status", snap)


class RefreshRequirementSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_chain_yields_red_when_blocking_open_rework(self) -> None:
        section = ProposalSection(
            id=701,
            proposal_id=601,
            title="Tech",
            status=SectionStatus.IN_PROGRESS,
        )
        requirement = TenderRequirement(
            id=1001,
            tender_id=42,
            requirement_text="SLA 99,9%.",
            priority="high",
            proposal_section_id=701,
            compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
        )
        requirement.proposal_section = section
        contribution = ContributionUnit(
            id=801,
            tender_id=42,
            proposal_section_id=701,
            title="C",
            status=ContributionUnitStatus.REWORK,
        )
        rework = ReworkAction(
            id=901,
            contribution_unit_id=801,
            severity="high",
            is_blocking=True,
            status=ReworkStatus.OPEN,
        )

        def handler_requirement(sql: str):
            if "from tender_requirements" in sql and "where tender_requirements.id" in sql:
                return [requirement]
            return None

        def handler_contributions(sql: str):
            if "from contribution_units" in sql:
                return [contribution]
            return None

        def handler_reworks(sql: str):
            if "from rework_actions" in sql:
                return [rework]
            return None

        def handler_gates(sql: str):
            if "from compliance_gates" in sql:
                return []
            return None

        session = _RoutingSession(
            handlers=[handler_requirement, handler_contributions, handler_reworks, handler_gates]
        )
        graph = _FakeGraphRetriever()
        engine = _FakeRagEngine(graph=graph)

        result = await refresh_requirement_snapshot(
            rag_engine=engine, db=session, requirement_id=1001
        )

        self.assertTrue(result.projected)
        self.assertTrue(result.snapshot_updated)
        self.assertEqual(result.snapshot_delta["risk_level"], "red")
        self.assertEqual(result.snapshot_delta["current_status"], "partially_addressed")
        self.assertEqual(result.snapshot_delta["coverage_status"], "draft")
        self.assertEqual(result.snapshot_delta["gate_state"], "none")

    async def test_returns_not_found_when_requirement_missing(self) -> None:
        session = _RoutingSession(handlers=[lambda _sql: []])
        engine = _FakeRagEngine()
        result = await refresh_requirement_snapshot(
            rag_engine=engine, db=session, requirement_id=999
        )
        self.assertFalse(result.projected)
        self.assertEqual(result.error, "requirement not found")


class ExplainRequirementPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_snapshot_and_events(self) -> None:
        graph = _FakeGraphRetriever()
        graph.lifecycle_payload = {
            "snapshot": {"current_status": "in_review", "risk_level": "amber"},
            "events": [
                {
                    "external_event_id": "evt-1",
                    "event_type": "review_changes_requested",
                    "occurred_at": "2026-04-18T08:00:00+00:00",
                }
            ],
        }
        engine = _FakeRagEngine(graph=graph)
        result = await explain_requirement_path(
            rag_engine=engine, tender_id=42, requirement_id=1001
        )
        self.assertEqual(result["node_id"], "tender-42-requirement-1001")
        self.assertEqual(result["snapshot"]["risk_level"], "amber")
        self.assertEqual(len(result["events"]), 1)

    async def test_returns_empty_when_engine_missing(self) -> None:
        result = await explain_requirement_path(rag_engine=None, tender_id=1, requirement_id=2)
        self.assertEqual(result["snapshot"], {})
        self.assertEqual(result["events"], [])
        self.assertEqual(result["node_id"], "tender-1-requirement-2")


class ProjectWorkflowEventsTests(unittest.IsolatedAsyncioTestCase):
    async def test_fans_out_event_to_each_linked_requirement(self) -> None:
        contribution = ContributionUnit(
            id=801,
            tender_id=42,
            proposal_section_id=701,
            title="C",
        )
        req_a = TenderRequirement(
            id=1001,
            tender_id=42,
            requirement_text="A",
            proposal_section_id=701,
        )
        req_b = TenderRequirement(
            id=1002,
            tender_id=42,
            requirement_text="B",
            proposal_section_id=701,
        )

        def handler_requirements(sql: str):
            if "from tender_requirements" in sql and "proposal_section_id" in sql:
                return [req_a, req_b]
            return None

        session = _RoutingSession(handlers=[handler_requirements])
        graph = _FakeGraphRetriever()
        engine = _FakeRagEngine(graph=graph)

        events = [
            (
                "review_approved",
                {"external_review_cycle_id": "55", "completed_at": "2026-04-19T10:00:00+00:00"},
            )
        ]
        results = await project_workflow_events(
            db=session,
            rag_engine=engine,
            tender_id=42,
            contribution=contribution,
            events=events,
            actor_id=7,
        )

        self.assertEqual(len(results), 2)
        node_ids = {result.requirement_node_id for result in results}
        self.assertEqual(
            node_ids,
            {"tender-42-requirement-1001", "tender-42-requirement-1002"},
        )
        # Two events appended (one per requirement) and two snapshot updates.
        self.assertEqual(len(graph.events), 2)
        self.assertEqual(len(graph.snapshots), 2)

    async def test_skips_when_no_linked_requirements(self) -> None:
        contribution = ContributionUnit(
            id=801,
            tender_id=42,
            proposal_section_id=701,
            title="C",
        )
        session = _RoutingSession(handlers=[lambda _sql: []])
        graph = _FakeGraphRetriever()
        engine = _FakeRagEngine(graph=graph)
        results = await project_workflow_events(
            db=session,
            rag_engine=engine,
            tender_id=42,
            contribution=contribution,
            events=[("review_approved", {})],
        )
        self.assertEqual(results, [])
        self.assertEqual(graph.events, [])
        self.assertEqual(graph.snapshots, [])


class ActiveEngineRegistryTests(unittest.TestCase):
    def test_set_and_get_active_engine(self) -> None:
        sentinel = object()
        try:
            set_active_rag_engine(sentinel)
            self.assertIs(get_active_rag_engine(), sentinel)
        finally:
            set_active_rag_engine(None)
        self.assertIsNone(get_active_rag_engine())


reconcile_tender_lifecycle_projection = _PROJECTOR.reconcile_tender_lifecycle_projection
ProjectionResult = _PROJECTOR.ProjectionResult


class ReconcileTenderLifecycleProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_unavailable_when_no_engine_registered(self) -> None:
        try:
            set_active_rag_engine(None)
            result = await reconcile_tender_lifecycle_projection(
                rag_engine=None,
                db=_RoutingSession(handlers=[]),
                tender_id=42,
            )
        finally:
            set_active_rag_engine(None)

        self.assertEqual(result["tender_id"], 42)
        self.assertEqual(result["requirements_seen"], 0)
        self.assertEqual(result["requirements_projected"], 0)
        self.assertEqual(result["requirements_failed"], 0)
        self.assertIn("graph retriever unavailable", result["errors"])

    async def test_projects_every_requirement_when_refresh_succeeds(self) -> None:
        req_a = TenderRequirement(id=1001, tender_id=42, requirement_text="A", priority="high")
        req_b = TenderRequirement(id=1002, tender_id=42, requirement_text="B", priority="medium")

        def handler_requirements(sql: str):
            if "from tender_requirements" in sql and "tender_id" in sql:
                return [req_a, req_b]
            return None

        session = _RoutingSession(handlers=[handler_requirements])
        engine = _FakeRagEngine()

        async def fake_refresh(*, rag_engine, db, requirement_id):
            return ProjectionResult(
                projected=True,
                snapshot_updated=True,
                requirement_node_id=f"tender-42-requirement-{requirement_id}",
                snapshot_delta={"current_status": "tracked"},
            )

        with patch.object(_PROJECTOR, "refresh_requirement_snapshot", fake_refresh):
            result = await reconcile_tender_lifecycle_projection(
                rag_engine=engine, db=session, tender_id=42
            )

        self.assertEqual(result["tender_id"], 42)
        self.assertEqual(result["requirements_seen"], 2)
        self.assertEqual(result["requirements_projected"], 2)
        self.assertEqual(result["requirements_failed"], 0)
        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(result["last_projected_at"])

    async def test_partial_failure_is_reported_without_aborting(self) -> None:
        req_ok = TenderRequirement(id=1001, tender_id=42, requirement_text="A", priority="high")
        req_bad = TenderRequirement(id=1002, tender_id=42, requirement_text="B", priority="high")
        req_crash = TenderRequirement(id=1003, tender_id=42, requirement_text="C", priority="high")

        def handler_requirements(sql: str):
            if "from tender_requirements" in sql and "tender_id" in sql:
                return [req_ok, req_bad, req_crash]
            return None

        session = _RoutingSession(handlers=[handler_requirements])
        engine = _FakeRagEngine()

        async def fake_refresh(*, rag_engine, db, requirement_id):
            if requirement_id == 1002:
                return ProjectionResult(
                    projected=False,
                    snapshot_updated=False,
                    requirement_node_id=f"tender-42-requirement-{requirement_id}",
                    snapshot_delta={},
                    error="graph write failed",
                )
            if requirement_id == 1003:
                raise RuntimeError("connection reset")
            return ProjectionResult(
                projected=True,
                snapshot_updated=True,
                requirement_node_id=f"tender-42-requirement-{requirement_id}",
                snapshot_delta={"current_status": "tracked"},
            )

        with patch.object(_PROJECTOR, "refresh_requirement_snapshot", fake_refresh):
            result = await reconcile_tender_lifecycle_projection(
                rag_engine=engine, db=session, tender_id=42
            )

        self.assertEqual(result["requirements_seen"], 3)
        self.assertEqual(result["requirements_projected"], 1)
        self.assertEqual(result["requirements_failed"], 2)
        error_ids = {entry["requirement_id"] for entry in result["errors"]}
        self.assertEqual(error_ids, {1002, 1003})
        crashed = next(entry for entry in result["errors"] if entry["requirement_id"] == 1003)
        self.assertIn("connection reset", crashed["error"])


if __name__ == "__main__":
    unittest.main()
