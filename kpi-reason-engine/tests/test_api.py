"""Endpoint tests for the Sprint 1 KPI reason engine scaffold."""

import unittest

from fastapi.testclient import TestClient

from app.main import app


class KpiReasonEngineApiTests(unittest.TestCase):
    """Contract tests for the tw-kpi-reason-engine FastAPI app."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_health_endpoint_returns_service_metadata(self) -> None:
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

    def test_tender_sync_endpoint_accepts_payload(self) -> None:
        response = self.client.post(
            "/v1/tenders",
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

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["external_tender_id"], "TEN-001")

    def test_event_ingestion_endpoint_accepts_event_payload(self) -> None:
        response = self.client.post(
            "/v1/tenders/TEN-001/events",
            json={
                "event_type": "tender_created",
                "occurred_at": "2026-03-14T09:00:00Z",
                "actor_id": "admin-1",
                "source": "tw-backend",
                "schema_version": "1.0.0",
                "payload": {"title": "Large Framework Tender"},
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["event_type"], "tender_created")

    def test_document_context_endpoint_accepts_payload(self) -> None:
        response = self.client.post(
            "/v1/tenders/TEN-001/documents/context",
            json={
                "document_id": "DOC-1",
                "document_type": "notice",
                "filename": "notice.pdf",
                "extracted_text_ref": "minio://docs/notice.txt",
                "metadata": {"pages": 12},
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["external_tender_id"], "TEN-001")

    def test_analysis_job_endpoint_accepts_payload(self) -> None:
        response = self.client.post(
            "/v1/tenders/TEN-001/analysis-jobs",
            json={
                "job_type": "full_recompute",
                "requested_by": "admin-1",
                "priority": "high",
                "reason": "Manual refresh",
                "metadata": {"source": "admin-ui"},
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["job_type"], "full_recompute")

    def test_snapshot_endpoint_returns_not_ready_placeholder(self) -> None:
        response = self.client.get("/v1/tenders/TEN-001/snapshot")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["external_tender_id"], "TEN-001")
        self.assertEqual(len(payload["kpis"]), 10)
        self.assertEqual({item["kpi_code"] for item in payload["kpis"]}, {"A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "Q", "E"})

    def test_diagnostics_endpoint_returns_not_ready_placeholder(self) -> None:
        response = self.client.get("/v1/tenders/TEN-001/diagnostics")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["external_tender_id"], "TEN-001")
        self.assertEqual(payload["summary"], "Diagnostics are not implemented in Sprint 1.")

    def test_transitions_endpoint_returns_placeholder_item(self) -> None:
        response = self.client.get("/v1/tenders/TEN-001/transitions")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["external_tender_id"], "TEN-001")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["from_state"], "S0")
        self.assertEqual(payload["items"][0]["to_state"], "S0")

    def test_forecast_endpoint_returns_placeholder_scenario(self) -> None:
        response = self.client.get("/v1/tenders/TEN-001/forecast")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["external_tender_id"], "TEN-001")
        self.assertEqual(len(payload["scenarios"]), 1)
        self.assertEqual(payload["scenarios"][0]["name"], "not_ready")

    def test_admin_portfolio_endpoints_return_placeholder_payloads(self) -> None:
        overview_response = self.client.get("/v1/admin/portfolio/overview")
        bottlenecks_response = self.client.get("/v1/admin/portfolio/bottlenecks")

        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(overview_response.json()["status"], "not_ready")
        self.assertEqual(overview_response.json()["portfolio_health"], "unknown")

        self.assertEqual(bottlenecks_response.status_code, 200)
        self.assertEqual(bottlenecks_response.json()["status"], "not_ready")
        self.assertEqual(len(bottlenecks_response.json()["items"]), 1)
        self.assertEqual(bottlenecks_response.json()["items"][0]["bottleneck_type"], "not_ready")


if __name__ == "__main__":
    unittest.main()
