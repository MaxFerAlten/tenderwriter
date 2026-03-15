"""API-level tests for the admin KPI BFF proxy."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.api.auth import UserResponse, get_current_user
from app.api.kpi_admin import router
from app.db.database import get_db
from app.services.kpi_reason_engine import KpiClientResult


class _MockKpiClient:
    def __init__(self, *, snapshot_result: KpiClientResult | None = None, recompute_result: KpiClientResult | None = None) -> None:
        self.snapshot_result = snapshot_result or KpiClientResult(True, 200, {"external_tender_id": "12", "status": "not_ready"})
        self.recompute_result = recompute_result or KpiClientResult(True, 202, {"external_tender_id": "12", "job_id": 81, "job_status": "queued"})
        self.analysis_job_calls: list[tuple[str, dict[str, object]]] = []

    async def get_tender_snapshot(self, external_tender_id: str) -> KpiClientResult:
        return self.snapshot_result

    async def request_analysis_job(self, external_tender_id: str, payload: dict[str, object]) -> KpiClientResult:
        self.analysis_job_calls.append((external_tender_id, payload))
        return self.recompute_result

    async def get_latest_analysis_job(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "job_status": "running"})

    async def get_portfolio_overview(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "not_ready", "total_tenders": 0, "tenders_by_health": {}, "portfolio_health": "unknown"})

    async def get_portfolio_bottlenecks(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "not_ready", "items": []})

    async def get_tender_diagnostics(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "findings": []})

    async def get_tender_transitions(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "items": [], "requirement_items": [], "history_items": []})

    async def get_tender_forecast(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "overall_confidence": 0.5, "scenarios": []})


class KpiAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/admin/kpi")
        app.dependency_overrides[get_current_user] = lambda: UserResponse(id=1, email="admin@test.local", name="Admin", role="admin")
        app.dependency_overrides[get_db] = lambda: object()
        cls.client = TestClient(app)

    def test_snapshot_query_falls_back_when_kpi_service_is_unavailable(self) -> None:
        mock_client = _MockKpiClient(
            snapshot_result=KpiClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message="KPI service timeout",
            )
        )
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/snapshot")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["external_tender_id"], "12")
        self.assertEqual(payload["health"], "unknown")
        self.assertEqual(payload["notes"], ["KPI service timeout"])
        self.assertTrue(payload["degraded"])
        self.assertEqual(payload["degraded_reason"], "KPI service timeout")

    def test_recompute_endpoint_resyncs_tender_before_requesting_analysis_job(self) -> None:
        mock_client = _MockKpiClient(
            recompute_result=KpiClientResult(
                delivered=True,
                status_code=202,
                response_json={
                    "external_tender_id": "12",
                    "job_id": 81,
                    "job_type": "full_recompute",
                    "job_status": "queued",
                },
            )
        )
        sync_mock = AsyncMock(return_value=KpiClientResult(True, 202, {"external_tender_id": "12"}))
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client), patch("app.api.kpi_admin._sync_tender_before_analysis_job", sync_mock):
            response = self.client.post("/admin/kpi/tenders/12/recompute")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["job_id"], 81)
        self.assertEqual(payload["job_status"], "queued")
        self.assertTrue(payload["tender_sync"]["delivered"])
        self.assertEqual(len(mock_client.analysis_job_calls), 1)
        sync_mock.assert_awaited_once()

    def test_recompute_returns_502_when_tender_resync_fails(self) -> None:
        mock_client = _MockKpiClient()
        sync_mock = AsyncMock(return_value=KpiClientResult(False, None, {}, "KPI service timeout"))
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client), patch("app.api.kpi_admin._sync_tender_before_analysis_job", sync_mock):
            response = self.client.post("/admin/kpi/tenders/12/recompute")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "KPI service timeout")
        self.assertEqual(len(mock_client.analysis_job_calls), 0)
        sync_mock.assert_awaited_once()

    def test_backfill_endpoint_resyncs_tender_before_requesting_analysis_job(self) -> None:
        mock_client = _MockKpiClient(
            recompute_result=KpiClientResult(
                delivered=True,
                status_code=202,
                response_json={
                    "external_tender_id": "12",
                    "job_id": 91,
                    "job_type": "history_backfill",
                    "job_status": "queued",
                },
            )
        )
        sync_mock = AsyncMock(return_value=KpiClientResult(True, 202, {"external_tender_id": "12"}))
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client), patch("app.api.kpi_admin._sync_tender_before_analysis_job", sync_mock):
            response = self.client.post("/admin/kpi/tenders/12/history/backfill")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["job_id"], 91)
        self.assertEqual(payload["job_type"], "history_backfill")
        self.assertEqual(payload["job_status"], "queued")
        self.assertTrue(payload["tender_sync"]["delivered"])
        self.assertEqual(len(mock_client.analysis_job_calls), 1)
        sync_mock.assert_awaited_once()

    def test_forecast_query_preserves_rich_payload(self) -> None:
        mock_client = _MockKpiClient()

        async def rich_forecast(external_tender_id: str) -> KpiClientResult:
            return KpiClientResult(True, 200, {
                "external_tender_id": external_tender_id,
                "status": "not_ready",
                "summary": "Forecast leans toward submission.",
                "overall_confidence": 0.72,
                "scenarios": [
                    {
                        "name": "submit_on_time",
                        "probability": 0.61,
                        "description": "Submission path remains viable.",
                        "confidence": 0.74,
                        "drivers": ["Q remains stable"],
                        "recommended_action": "Protect the submission path.",
                    }
                ],
            })

        mock_client.get_tender_forecast = rich_forecast
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/forecast")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["upstream_status_code"], 200)
        self.assertEqual(payload["scenarios"][0]["name"], "submit_on_time")
        self.assertEqual(payload["scenarios"][0]["drivers"], ["Q remains stable"])

    def test_latest_analysis_job_falls_back_to_degraded_state(self) -> None:
        mock_client = _MockKpiClient()

        async def failing_latest_job(external_tender_id: str) -> KpiClientResult:
            return KpiClientResult(False, None, {}, "KPI service timeout")

        mock_client.get_latest_analysis_job = failing_latest_job
        with patch("app.api.kpi_admin.KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/analysis-jobs/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["job_status"], "degraded")
        self.assertEqual(payload["error_message"], "KPI service timeout")


if __name__ == "__main__":
    unittest.main()
