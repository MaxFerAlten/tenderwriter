"""Endpoint tests for the KPI reason engine authenticated ingestion flow."""

import os
import shutil
import tempfile
import time
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

    def test_store_schema_version_matches_current_migration(self) -> None:
        self.assertEqual(self.client.app.state.store.get_schema_version(), "20260315_0003")


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
        self.assertIn("Tracked analysis jobs: 1.", diagnostics["findings"])

    def test_snapshot_for_missing_tender_returns_not_ready_placeholder(self) -> None:
        response = self.client.get(
            "/v1/tenders/TEN-404/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertEqual(response.json()["notes"], ["Tender not synchronized yet."])

    def test_analysis_job_worker_processes_recompute_and_exposes_latest_status(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-ASYNC",
                "title": "Async Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
                "current_status": "draft",
                "departments": ["sales"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide a company profile",
                        "priority": "medium",
                        "compliance_status": "partially_addressed",
                        "mapped_section_id": "SEC-1",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Company profile",
                        "owner_department": "sales",
                        "status": "in_progress",
                    }
                ],
                "metadata": {"priority": "medium"},
            },
        )

        request_response = self.client.post(
            "/v1/tenders/TEN-ASYNC/analysis-jobs",
            headers=self._auth_headers(),
            json={
                "job_type": "full_recompute",
                "requested_by": "admin-1",
                "priority": "high",
                "reason": "Manual refresh",
                "metadata": {"source": "admin-ui"},
            },
        )

        self.assertEqual(request_response.status_code, 202)
        accepted = request_response.json()
        self.assertEqual(accepted["job_status"], "queued")
        self.assertIsNotNone(accepted["job_id"])

        latest_job: dict[str, object] | None = None
        for _ in range(40):
            latest_response = self.client.get(
                "/v1/tenders/TEN-ASYNC/analysis-jobs/latest",
                headers=self._auth_headers(),
            )
            self.assertEqual(latest_response.status_code, 200)
            latest_job = latest_response.json()
            if latest_job["job_status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(latest_job)
        self.assertEqual(latest_job["job_status"], "succeeded")
        self.assertIsNotNone(latest_job["latest_snapshot_generated_at"])
        snapshot_record = self.client.app.state.store.get_latest_snapshot_record("TEN-ASYNC")
        self.assertIsNotNone(snapshot_record)
        self.assertEqual(latest_job["latest_snapshot_generated_at"].replace("Z", "+00:00"), snapshot_record["generated_at"])

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
        a2 = next(score for score in snapshot["kpis"] if score["kpi_code"] == "A2")
        a3 = next(score for score in snapshot["kpis"] if score["kpi_code"] == "A3")
        a4 = next(score for score in snapshot["kpis"] if score["kpi_code"] == "A4")
        q = next(score for score in snapshot["kpis"] if score["kpi_code"] == "Q")
        self.assertEqual(snapshot["analytical_phase"], "S4")
        self.assertEqual(snapshot["health"], "amber")
        self.assertEqual(a1["value"], 67.5)
        self.assertEqual(a1["health"], "amber")
        self.assertEqual(a1["provenance"], "measured")
        self.assertEqual(a4["value"], 65.5)
        self.assertEqual(a4["health"], "amber")
        self.assertIsNotNone(a2["value"])
        self.assertIsNotNone(a3["value"])
        self.assertIsNotNone(q["value"])
        self.assertTrue(a2["recommendation"])
        self.assertTrue(a3["recommendation"])
        self.assertEqual(snapshot["analysis_metadata"]["formula_bundle_version"], "quality-formulas-v2")
        self.assertIn("A3", snapshot["analysis_metadata"]["scored_kpis"])
        self.assertEqual(a2["formula_version"], "editorial-quality-v1")
        stored = self.client.app.state.store.get_tender("TEN-777")
        self.assertEqual(stored["health"], "amber")
        self.assertEqual(stored["analytical_phase"], "S4")

    def test_snapshot_persistence_is_deduplicated_and_uses_persisted_timestamp(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-DEDUPE",
                "title": "Persistent Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
                "current_status": "draft",
                "departments": ["sales"],
                "requirement_contexts": [
                    {
                        "external_requirement_id": "REQ-1",
                        "reference": "1.1",
                        "summary": "Provide a company profile",
                        "priority": "medium",
                        "compliance_status": "partially_addressed",
                        "mapped_section_id": "SEC-1",
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Company profile",
                        "owner_department": "sales",
                        "status": "in_progress",
                    }
                ],
                "metadata": {"priority": "medium"},
            },
        )

        first_snapshot = self.client.get(
            "/v1/tenders/TEN-DEDUPE/snapshot",
            headers=self._auth_headers(),
        )
        second_snapshot = self.client.get(
            "/v1/tenders/TEN-DEDUPE/snapshot",
            headers=self._auth_headers(),
        )

        self.assertEqual(first_snapshot.status_code, 200)
        self.assertEqual(second_snapshot.status_code, 200)

        store = self.client.app.state.store
        self.assertEqual(store.count_snapshots("TEN-DEDUPE"), 1)
        snapshot_record = store.get_latest_snapshot_record("TEN-DEDUPE")
        self.assertIsNotNone(snapshot_record)
        self.assertEqual(first_snapshot.json()["generated_at"].replace("Z", "+00:00"), snapshot_record["generated_at"])
        self.assertEqual(second_snapshot.json()["generated_at"].replace("Z", "+00:00"), snapshot_record["generated_at"])

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

    def test_findings_and_phase_transitions_are_persisted(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-HISTORY",
                "title": "History Tender",
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
                    "stage_name": "quality_review",
                },
            },
            {
                "event_type": "rework_requested",
                "occurred_at": "2026-03-15T08:20:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C-1",
                    "external_rework_id": "RW-1",
                    "severity": "high",
                    "is_blocking": True,
                    "reason": "signature missing",
                },
            },
            {
                "event_type": "compliance_gate_opened",
                "occurred_at": "2026-03-15T08:30:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_gate_id": "G-1",
                    "gate_name": "Auto compliance readiness",
                },
            },
            {
                "event_type": "compliance_gate_failed",
                "occurred_at": "2026-03-15T08:40:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_gate_id": "G-1",
                    "gate_name": "Auto compliance readiness",
                    "status": "failed",
                    "decision_notes": "signed annex still missing",
                },
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-HISTORY/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        diagnostics_response = self.client.get(
            "/v1/tenders/TEN-HISTORY/diagnostics",
            headers=self._auth_headers(),
        )
        transitions_response = self.client.get(
            "/v1/tenders/TEN-HISTORY/transitions",
            headers=self._auth_headers(),
        )

        self.assertEqual(diagnostics_response.status_code, 200)
        self.assertEqual(transitions_response.status_code, 200)

        store = self.client.app.state.store
        self.assertGreater(store.count_findings("TEN-HISTORY"), 0)
        self.assertEqual(store.count_phase_transitions("TEN-HISTORY"), 4)

        snapshot_record = store.get_latest_snapshot_record("TEN-HISTORY")
        self.assertIsNotNone(snapshot_record)
        self.assertEqual(snapshot_record["analytical_phase"], "S6")
        self.assertEqual(transitions_response.json()["items"][0]["to_state"], "S8")
        self.assertEqual(transitions_response.json()["generated_at"].replace("Z", "+00:00"), snapshot_record["generated_at"])
        self.assertIn("A1", " ".join(snapshot_record["findings"]))
        self.assertEqual(snapshot_record["analysis_metadata"]["formula_bundle_version"], "quality-formulas-v2")
        self.assertEqual(diagnostics_response.json()["analysis_metadata"]["model_bundle_version"], "deterministic-proxy-model-v2")
        self.assertIn("formula=editorial-quality-v1", " ".join(snapshot_record["findings"]))

    def test_transitions_endpoint_surfaces_phase_drivers_and_requirement_focus(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-TRANS",
                "title": "Transition Tender",
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
                    "stage_name": "quality_review",
                },
            },
            {
                "event_type": "rework_requested",
                "occurred_at": "2026-03-15T08:20:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C-1",
                    "external_rework_id": "RW-1",
                    "severity": "high",
                    "is_blocking": True,
                    "reason": "signature missing",
                },
            },
            {
                "event_type": "compliance_gate_opened",
                "occurred_at": "2026-03-15T08:30:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_gate_id": "G-1",
                    "gate_name": "Auto compliance readiness",
                },
            },
            {
                "event_type": "compliance_gate_failed",
                "occurred_at": "2026-03-15T08:40:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_gate_id": "G-1",
                    "gate_name": "Auto compliance readiness",
                    "status": "failed",
                    "decision_notes": "signed annex still missing",
                },
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-TRANS/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        transitions_response = self.client.get(
            "/v1/tenders/TEN-TRANS/transitions",
            headers=self._auth_headers(),
        )

        self.assertEqual(transitions_response.status_code, 200)
        transitions = transitions_response.json()
        self.assertIn("S8", transitions["summary"])
        self.assertEqual(transitions["items"][0]["to_state"], "S8")
        self.assertEqual(transitions["items"][0]["source_event_type"], "compliance_gate_failed")
        self.assertEqual(transitions["requirement_items"][0]["driver_phase"], "S8")
        self.assertEqual(transitions["requirement_items"][0]["last_event_type"], "compliance_gate_failed")


    def test_forecast_endpoint_returns_rule_based_scenarios(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-FORECAST",
                "title": "Forecast Tender",
                "customer_name": "Northwind",
                "due_at": "2030-04-30T10:00:00Z",
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
                    }
                ],
                "section_contexts": [
                    {
                        "external_section_id": "SEC-1",
                        "title": "Security",
                        "owner_department": "sales",
                        "status": "approved",
                    }
                ],
                "metadata": {"priority": "high"},
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
                "event_type": "proposal_section_updated",
                "occurred_at": "2026-03-15T08:10:00Z",
                "source": "tw-backend",
                "payload": {"external_section_id": "SEC-1"},
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-FORECAST/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        forecast_response = self.client.get(
            "/v1/tenders/TEN-FORECAST/forecast",
            headers=self._auth_headers(),
        )

        self.assertEqual(forecast_response.status_code, 200)
        forecast = forecast_response.json()
        self.assertTrue(forecast["summary"])
        self.assertIsNotNone(forecast["overall_confidence"])
        self.assertEqual(len(forecast["scenarios"]), 3)
        self.assertEqual(forecast["scenarios"][0]["name"], "submit_on_time")
        self.assertGreater(len(forecast["scenarios"][0]["drivers"]), 0)
        self.assertTrue(forecast["scenarios"][0]["recommended_action"])

    def test_history_backfill_job_persists_reconstructed_history(self) -> None:
        self.client.post(
            "/v1/tenders",
            headers=self._auth_headers(),
            json={
                "external_tender_id": "TEN-BACKFILL",
                "title": "Backfill Tender",
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
                    "stage_name": "quality_review",
                },
            },
            {
                "event_type": "rework_requested",
                "occurred_at": "2026-03-15T08:20:00Z",
                "source": "tw-backend",
                "payload": {
                    "external_contribution_id": "C-1",
                    "external_rework_id": "RW-1",
                    "severity": "high",
                    "is_blocking": True,
                    "reason": "signature missing",
                },
            },
        ]:
            response = self.client.post(
                "/v1/tenders/TEN-BACKFILL/events",
                headers=self._auth_headers(),
                json=payload,
            )
            self.assertEqual(response.status_code, 202)

        request_response = self.client.post(
            "/v1/tenders/TEN-BACKFILL/analysis-jobs",
            headers=self._auth_headers(),
            json={
                "job_type": "history_backfill",
                "requested_by": "admin-1",
                "priority": "high",
                "reason": "Manual history replay",
                "metadata": {"source": "admin-ui"},
            },
        )
        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.json()["job_status"], "queued")

        latest_job = None
        for _ in range(40):
            latest_response = self.client.get(
                "/v1/tenders/TEN-BACKFILL/analysis-jobs/latest",
                headers=self._auth_headers(),
            )
            self.assertEqual(latest_response.status_code, 200)
            latest_job = latest_response.json()
            if latest_job["job_status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(latest_job)
        self.assertEqual(latest_job["job_status"], "succeeded")

        transitions_response = self.client.get(
            "/v1/tenders/TEN-BACKFILL/transitions",
            headers=self._auth_headers(),
        )
        self.assertEqual(transitions_response.status_code, 200)
        history_items = transitions_response.json()["history_items"]
        self.assertGreaterEqual(len(history_items), 3)
        self.assertTrue(any(item["reconstructed"] for item in history_items))
        self.assertTrue(any(item["replay_source_event_type"] == "rework_requested" for item in history_items))

        snapshot_record = self.client.app.state.store.get_latest_snapshot_record("TEN-BACKFILL")
        self.assertIsNotNone(snapshot_record)
        self.assertFalse(snapshot_record["analysis_metadata"].get("reconstructed", False))
        self.assertEqual(snapshot_record["analysis_metadata"].get("source_job_type"), "history_backfill")
        self.assertEqual(latest_job["latest_snapshot_generated_at"].replace("Z", "+00:00"), snapshot_record["generated_at"])
