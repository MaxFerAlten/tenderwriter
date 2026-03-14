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
