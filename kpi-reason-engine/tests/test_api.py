"""Endpoint tests for the KPI reason engine authenticated ingestion flow."""

import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

_TEST_DIR = tempfile.mkdtemp(prefix="kpi-reason-engine-tests-")
os.environ["KPI_REASON_ENGINE_SERVICE_TOKEN"] = "test-kpi-token"
os.environ["KPI_REASON_ENGINE_DATABASE_PATH"] = os.path.join(_TEST_DIR, "kpi_reason_engine.db")

from app.main import app


class KpiReasonEngineApiTests(unittest.TestCase):
    """Contract and persistence tests for the tw-kpi-reason-engine FastAPI app."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        shutil.rmtree(_TEST_DIR, ignore_errors=True)

    def setUp(self) -> None:
        self.client.app.state.store.clear_all()

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        return {
            "Authorization": "Bearer test-kpi-token",
            "X-Service-Token": "test-kpi-token",
        }

    def test_health_endpoint_returns_service_metadata_without_auth(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "healthy",
                "service": "tw-kpi-reason-engine",
                "version": "0.1.0",
            },
        )

    def test_protected_routes_require_service_credentials(self) -> None:
        response = self.client.post(
            "/v1/tenders",
            json={
                "external_tender_id": "TEN-001",
                "title": "Large Framework Tender",
                "departments": [],
                "requirement_contexts": [],
                "section_contexts": [],
                "metadata": {},
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Missing or invalid service credentials.")

    def test_tender_sync_persists_mirror_and_snapshot_uses_store(self) -> None:
        response = self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-001",
                "title": "Large Framework Tender",
                "customer_name": "ACME",
                "due_at": "2026-03-31T10:00:00Z",
                "current_status": "draft",
                "departments": ["legal", "sales"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.2",
                        "summary": "Need ISO certification",
                        "priority": "high",
                        "compliance_status": "not_addressed",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Company profile",
                        "owner_department": "sales",
                        "status": "draft",
                    }
                ],
                "metadata": {"priority": "high"},
            },
        )
        snapshot_response = self.client.get(
            "/v1/tenders/TEN-001/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(snapshot_response.status_code, 200)
        snapshot = snapshot_response.json()
        self.assertEqual(snapshot["status"], "not_ready")
        self.assertEqual(snapshot["external_tender_id"], "TEN-001")
        self.assertEqual(snapshot["health"], "unknown")
        self.assertEqual(snapshot["analytical_phase"], "S0")
        self.assertIn("Tender mirror synchronized", snapshot["notes"][0])
        stored = self.client.app.state.store.get_tender("TEN-001")
        self.assertEqual(stored["title"], "Large Framework Tender")
        self.assertEqual(stored["customer_name"], "ACME")
        self.assertEqual(stored["section_contexts"][0]["external_section_id"], "SEC-1")

    def test_event_ingestion_is_idempotent_for_duplicate_payloads(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-001",
                "title": "Large Framework Tender",
                "departments": [],
                "requirement_contexts": [],
                "section_contexts": [],
                "metadata": {},
            },
        )
        payload = {
            "event_type": "tender_created",
            "occurred_at": "2026-03-14T09:00:00Z",
            "actor_id": "admin-1",
            "source": "tw-backend",
            "schema_version": "1.0.0",
            "payload": {"title": "Large Framework Tender"},
        }

        first = self.client.post(
            "/v1/tenders/TEN-001/events",
            headers=self._auth_headers(),
            json=payload,
        )
        second = self.client.post(
            "/v1/tenders/TEN-001/events",
            headers=self._auth_headers(),
            json=payload,
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(self.client.app.state.store.count_domain_events("TEN-001"), 1)

    def test_document_context_and_analysis_job_are_persisted(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-001",
                "title": "Large Framework Tender",
                "departments": [],
                "requirement_contexts": [],
                "section_contexts": [],
                "metadata": {},
            },
        )

        document_response = self.client.post(
            "/v1/tenders/TEN-001/documents/context",
            headers=self._auth_headers(),
            json={
                "document_id": "DOC-1",
                "document_type": "notice",
                "filename": "notice.pdf",
                "extracted_text_ref": "minio://docs/notice.txt",
                "metadata": {"pages": 12},
            },
        )
        job_response = self.client.post(
            "/v1/tenders/TEN-001/analysis-jobs",
            headers=self._auth_headers(),
            json={
                "job_type": "full_recompute",
                "requested_by": "admin-1",
                "priority": "high",
                "reason": "Manual refresh",
                "metadata": {"source": "admin-ui"},
            },
        )
        diagnostics_response = self.client.get(
            "/v1/tenders/TEN-001/diagnostics",
            headers=self._auth_headers(),
        )

        self.assertEqual(document_response.status_code, 202)
        self.assertEqual(job_response.status_code, 202)
        self.assertEqual(self.client.app.state.store.count_document_contexts("TEN-001"), 1)
        self.assertEqual(self.client.app.state.store.count_analysis_jobs("TEN-001"), 1)
        self.assertEqual(diagnostics_response.status_code, 200)
        diagnostics = diagnostics_response.json()
        self.assertIn("Stored document contexts: 1.", diagnostics["findings"])
        self.assertIn("Queued analysis jobs: 1.", diagnostics["findings"])

    def test_snapshot_for_missing_tender_returns_not_ready_placeholder(self) -> None:
        response = self.client.get(
            "/v1/tenders/TEN-404/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertEqual(response.json()["notes"], ["Tender not synchronized yet."])

    def test_partial_snapshot_scores_a1_and_a4_after_requirements_and_section_updates(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-777",
                "title": "Regional Tender",
                "customer_name": "Northwind",
                "due_at": "2026-04-30T10:00:00Z",
                "current_status": "active",
                "departments": ["sales"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide ISO 27001 evidence",
                        "priority": "high",
                        "compliance_status": "fully_addressed",
                        "mapped_section_id": "SEC-1",
                    },
                    {
                        "external_requirement_id": "REQ-2",
                        "reference": "1.2",
                        "summary": "Include continuity plan",
                        "priority": "medium",
                        "compliance_status": "not_addressed",
                    },
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Security",
                        "owner_department": "sales",
                        "status": "approved",
                    },
                    {
                        "external_section_id": "SEC-2",
                        "title": "Operations",
                        "owner_department": "sales",
                        "status": "in_progress",
                    },
                ],
                "metadata": {"priority": "high"},
            },
        )
        self.client.post(
            "/v1/tenders/TEN-777/events",
            headers=self._auth_headers(),
            json={
                "event_type": "tender_document_ingested",
                "occurred_at": "2026-03-14T09:00:00Z",
                "source": "tw-backend",
                "payload": {"document_id": "DOC-1"},
            },
        )
        self.client.post(
            "/v1/tenders/TEN-777/events",
            headers=self._auth_headers(),
            json={
                "event_type": "requirements_extracted",
                "occurred_at": "2026-03-14T09:01:00Z",
                "source": "tw-backend",
                "payload": {"requirement_count": 2},
            },
        )
        self.client.post(
            "/v1/tenders/TEN-777/events",
            headers=self._auth_headers(),
            json={
                "event_type": "proposal_section_updated",
                "occurred_at": "2026-03-14T09:02:00Z",
                "source": "tw-backend",
                "payload": {"external_section_id": "SEC-2"},
            },
        )

        snapshot_response = self.client.get(
            "/v1/tenders/TEN-777/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(snapshot_response.status_code, 200)
        snapshot = snapshot_response.json()
        a1 = next(score for score in snapshot["kpis"] if score["kpi_code"] == "A1")
        a4 = next(score for score in snapshot["kpis"] if score["kpi_code"] == "A4")
        self.assertEqual(snapshot["analytical_phase"], "S4")
        self.assertEqual(snapshot["health"], "amber")
        self.assertEqual(a1["value"], 67.5)
        self.assertEqual(a1["health"], "amber")
        self.assertEqual(a1["provenance"], "measured")
        self.assertEqual(a4["value"], 65.5)
        self.assertEqual(a4["health"], "amber")
        stored = self.client.app.state.store.get_tender("TEN-777")
        self.assertEqual(stored["health"], "amber")
        self.assertEqual(stored["analytical_phase"], "S4")

    def test_admin_portfolio_endpoints_reflect_persisted_tenders(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-001",
                "title": "Large Framework Tender",
                "departments": [],
                "requirement_contexts": [],
                "section_contexts": [],
                "metadata": {},
            },
        )
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-002",
                "title": "Regional Tender",
                "departments": [],
                "requirement_contexts": [],
                "section_contexts": [],
                "metadata": {},
            },
        )

        overview_response = self.client.get(
            "/v1/admin/portfolio/overview",
            headers=self._auth_headers(),
        )
        bottlenecks_response = self.client.get(
            "/v1/admin/portfolio/bottlenecks",
            headers=self._auth_headers(),
        )

        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(overview_response.json()["status"], "not_ready")
        self.assertEqual(overview_response.json()["total_tenders"], 2)
        self.assertEqual(overview_response.json()["tenders_by_health"], {"unknown": 2})

        self.assertEqual(bottlenecks_response.status_code, 200)
        self.assertEqual(bottlenecks_response.json()["status"], "not_ready")
        self.assertEqual(len(bottlenecks_response.json()["items"]), 2)
        self.assertEqual(bottlenecks_response.json()["items"][0]["bottleneck_type"], "analysis_pending")


if __name__ == "__main__":
    unittest.main()

class KpiReasonEngineOperationalAnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)

    def setUp(self) -> None:
        self.client.app.state.store.clear_all()

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        return {
            "Authorization": "Bearer test-kpi-token",
            "X-Service-Token": "test-kpi-token",
        }

    def test_operational_snapshot_scores_b1_b4_and_e(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-OPS",
                "title": "Operational Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
                "current_status": "in_progress",
                "departments": ["legal", "sales"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide signed annex",
                        "priority": "high",
                        "compliance_status": "fully_addressed",
                        "mapped_section_id": "SEC-1",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Compliance",
                        "owner_department": "legal",
                        "status": "approved",
                    }
                ],
                "metadata": {"priority": "high"},
            },
        )
        seed_events = [
            {
                "event_type": "tender_document_ingested",
                "occurred_at": "2026-03-15T08:00:00Z",
                "source": "tw-backend",
                "payload": {"document_id": "DOC-1"},
            },
            {
                "event_type": "requirements_extracted",
                "occurred_at": "2026-03-15T08:05:00Z",
                "source": "tw-backend",
                "payload": {"requirement_count": 1},
            },
            {
                "event_type": "contribution_request_created",
                "occurred_at": "2026-03-15T08:10:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C1",
                    "external_request_id": "R1",
                    "requested_at": "2026-03-15T08:00:00Z",
                    "due_at": "2026-03-16T08:00:00Z",
                    "sla_target_hours": 8,
                    "sla_max_hours": 24,
                },
            },
            {
                "event_type": "contribution_received",
                "occurred_at": "2026-03-15T14:00:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C1",
                    "external_request_id": "R1",
                    "requested_at": "2026-03-15T08:00:00Z",
                    "received_at": "2026-03-15T14:00:00Z",
                    "due_at": "2026-03-16T08:00:00Z",
                    "response_time_hours": 6,
                    "lateness_hours": 0,
                },
            },
            {
                "event_type": "contribution_request_created",
                "occurred_at": "2026-03-15T08:20:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C2",
                    "external_request_id": "R2",
                    "requested_at": "2026-03-15T08:00:00Z",
                    "due_at": "2026-03-16T08:00:00Z",
                    "sla_target_hours": 8,
                    "sla_max_hours": 24,
                },
            },
            {
                "event_type": "contribution_received",
                "occurred_at": "2026-03-16T20:00:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C2",
                    "external_request_id": "R2",
                    "requested_at": "2026-03-15T08:00:00Z",
                    "received_at": "2026-03-16T20:00:00Z",
                    "due_at": "2026-03-16T08:00:00Z",
                    "response_time_hours": 36,
                    "lateness_hours": 12,
                },
            },
            {
                "event_type": "rework_requested",
                "occurred_at": "2026-03-16T22:00:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C2",
                    "external_rework_id": "RW1",
                    "requested_at": "2026-03-16T22:00:00Z",
                    "severity": "high",
                    "is_blocking": True,
                },
            },
            {
                "event_type": "call_scheduled",
                "occurred_at": "2026-03-15T07:00:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_call_session_id": "CALL1",
                    "scheduled_at": "2026-03-15T09:00:00Z",
                },
            },
            {
                "event_type": "call_attendance_recorded",
                "occurred_at": "2026-03-15T09:05:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_call_session_id": "CALL1",
                    "attendance_record_id": "A1",
                    "attendee_label": "Legal team",
                    "attendance_status": "attended",
                },
            },
            {
                "event_type": "call_attendance_recorded",
                "occurred_at": "2026-03-15T09:05:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_call_session_id": "CALL1",
                    "attendance_record_id": "A2",
                    "attendee_label": "Sales team",
                    "attendance_status": "absent",
                },
            },
        ]
        for payload in seed_events:
            response = self.client.post(
                "/v1/tenders/TEN-OPS/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        snapshot_response = self.client.get(
            "/v1/tenders/TEN-OPS/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(snapshot_response.status_code, 200)
        snapshot = snapshot_response.json()
        scores = {item["kpi_code"]: item for item in snapshot["kpis"]}
        self.assertEqual(snapshot["analytical_phase"], "S6")
        self.assertEqual(snapshot["health"], "red")
        self.assertEqual(scores["B1"]["value"], 85.0)
        self.assertEqual(scores["B2"]["value"], 57.5)
        self.assertEqual(scores["B3"]["value"], 50.0)
        self.assertEqual(scores["B4"]["value"], 84.0)
        self.assertEqual(scores["E"]["value"], 71.2)
        self.assertEqual(scores["B1"]["provenance"], "measured")
        self.assertEqual(scores["B4"]["health"], "green")
    def test_snapshot_recognizes_contribution_review_started_for_s5_phase(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-REV",
                "title": "Review Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
                "current_status": "in_progress",
                "departments": ["legal"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide signed annex",
                        "priority": "high",
                        "compliance_status": "partially_addressed",
                        "mapped_section_id": "SEC-1",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Compliance",
                        "owner_department": "legal",
                        "status": "in_review",
                    }
                ],
                "metadata": {},
            },
        )
        for payload in [
            {
                "event_type": "tender_document_ingested",
                "occurred_at": "2026-03-15T08:00:00Z",
                "source": "tw-backend",
                "payload": {"document_id": "DOC-1"},
            },
            {
                "event_type": "requirements_extracted",
                "occurred_at": "2026-03-15T08:05:00Z",
                "source": "tw-backend",
                "payload": {"requirement_count": 1},
            },
            {
                "event_type": "contribution_review_started",
                "occurred_at": "2026-03-15T08:10:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C-1",
                    "external_review_cycle_id": "RV-1",
                    "stage_name": "proposal_section_review",
                },
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-REV/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        snapshot_response = self.client.get(
            "/v1/tenders/TEN-REV/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(snapshot_response.status_code, 200)
        snapshot = snapshot_response.json()
        self.assertEqual(snapshot["analytical_phase"], "S5")

    def test_snapshot_enters_s8_for_open_compliance_gate(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-GATE",
                "title": "Compliance Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
                "current_status": "in_progress",
                "departments": ["legal"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide signed annex",
                        "priority": "high",
                        "compliance_status": "not_addressed",
                        "mapped_section_id": "SEC-1",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Compliance",
                        "owner_department": "legal",
                        "status": "approved",
                    }
                ],
                "metadata": {},
            },
        )
        for payload in [
            {
                "event_type": "tender_document_ingested",
                "occurred_at": "2026-03-15T08:00:00Z",
                "source": "tw-backend",
                "payload": {"document_id": "DOC-1"},
            },
            {
                "event_type": "requirements_extracted",
                "occurred_at": "2026-03-15T08:05:00Z",
                "source": "tw-backend",
                "payload": {"requirement_count": 1},
            },
            {
                "event_type": "compliance_gate_opened",
                "occurred_at": "2026-03-15T08:10:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_gate_id": "G-1",
                    "gate_name": "Auto compliance readiness",
                },
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-GATE/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        snapshot_response = self.client.get(
            "/v1/tenders/TEN-GATE/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(snapshot_response.status_code, 200)
        snapshot = snapshot_response.json()
        self.assertEqual(snapshot["analytical_phase"], "S8")

