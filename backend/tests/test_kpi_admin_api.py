"""API-level tests for the admin KPI BFF proxy."""

import os
import sys
import unittest
from dataclasses import dataclass
from importlib import import_module
from typing import Any
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


@dataclass(slots=True)
class KpiClientResult:
    delivered: bool
    status_code: int | None
    response_json: dict[str, Any]
    error_message: str | None = None


class _FakeUserResponse:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


_KPI_ADMIN_TEST_MODULE = None


def _load_kpi_admin_module():
    global _KPI_ADMIN_TEST_MODULE
    if _KPI_ADMIN_TEST_MODULE is not None:
        return _KPI_ADMIN_TEST_MODULE

    fake_auth = import_module("types").ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return _FakeUserResponse(id=1, email="admin@test.local", name="Admin", role="admin")

    fake_auth.UserResponse = _FakeUserResponse
    fake_auth.get_current_user = _fake_get_current_user

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=object()),
        patch.dict(sys.modules, {"app.api.auth": fake_auth}),
    ):
        sys.modules.pop("app.api.kpi_admin", None)
        _KPI_ADMIN_TEST_MODULE = import_module("app.api.kpi_admin")
        return _KPI_ADMIN_TEST_MODULE


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

    async def get_service_health(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "healthy", "service": "tw-kpi-reason-engine", "version": "0.1.0", "ready": True})

    async def get_service_readiness(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "ready", "service": "tw-kpi-reason-engine", "version": "0.1.0", "ready": True, "warnings": [], "dependencies": []})

    async def get_version_manifest(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "available", "service": "tw-kpi-reason-engine", "version": "0.1.0", "entries": []})

    async def get_portfolio_overview(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "not_ready", "total_tenders": 0, "tenders_by_health": {}, "portfolio_health": "unknown", "analytical_phases": {}, "critical_tenders": []})

    async def get_portfolio_bottlenecks(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "not_ready", "items": []})

    async def get_portfolio_intelligence(self) -> KpiClientResult:
        return KpiClientResult(True, 200, {"status": "not_ready", "phase_hotspots": [], "risk_hotspots": [], "outcome_trends": {}, "watchlist": [], "notes": []})

    async def get_tender_diagnostics(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "findings": []})

    async def get_tender_transitions(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "items": [], "requirement_items": [], "history_items": []})

    async def get_tender_forecast(self, external_tender_id: str) -> KpiClientResult:
        return KpiClientResult(True, 200, {"external_tender_id": external_tender_id, "status": "not_ready", "summary": "ok", "overall_confidence": 0.5, "scenarios": []})


class KpiAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kpi_admin_module = _load_kpi_admin_module()
        app = FastAPI()
        app.include_router(cls.kpi_admin_module.router, prefix="/admin/kpi")
        app.dependency_overrides[cls.kpi_admin_module.get_current_user] = lambda: _FakeUserResponse(
            id=1,
            email="admin@test.local",
            name="Admin",
            role="admin",
        )
        app.dependency_overrides[cls.kpi_admin_module.get_db] = lambda: object()
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
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/snapshot")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["external_tender_id"], "12")
        self.assertEqual(payload["health"], "unknown")
        self.assertEqual(payload["notes"], ["KPI service timeout"])
        self.assertFalse(payload["analysis_metadata"]["shadow_mode_enabled"])
        self.assertEqual(payload["analysis_metadata"]["forecast_engine_active"], None)
        self.assertTrue(payload["degraded"])
        self.assertEqual(payload["degraded_reason"], "KPI service timeout")

    def test_portfolio_resync_reports_successes_and_failures(self) -> None:
        mock_client = _MockKpiClient()
        load_ids_mock = AsyncMock(return_value=[12, 18])
        sync_mock = AsyncMock(side_effect=[
            KpiClientResult(True, 202, {"external_tender_id": "12"}),
            KpiClientResult(False, 502, {}, "Upstream timeout"),
        ])
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client), patch.object(self.kpi_admin_module, "_load_portfolio_tender_ids", load_ids_mock), patch.object(self.kpi_admin_module, "_sync_tender_before_analysis_job", sync_mock):
            response = self.client.post("/admin/kpi/portfolio/resync")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_tenders"], 2)
        self.assertEqual(payload["synced_tenders"], 1)
        self.assertEqual(payload["failed_tenders"], 1)
        self.assertEqual(payload["items"][0]["tender_id"], 12)
        self.assertTrue(payload["items"][0]["delivered"])
        self.assertEqual(payload["items"][1]["tender_id"], 18)
        self.assertEqual(payload["items"][1]["error_message"], "Upstream timeout")
        load_ids_mock.assert_awaited_once()
        self.assertEqual(sync_mock.await_count, 2)

    def test_service_status_query_aggregates_runtime_payloads(self) -> None:
        mock_client = _MockKpiClient()

        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/service/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["health"]["status"], "healthy")
        self.assertEqual(payload["readiness"]["status"], "ready")
        self.assertEqual(payload["version_manifest"]["status"], "available")

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
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client), patch.object(self.kpi_admin_module, "_sync_tender_before_analysis_job", sync_mock):
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
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client), patch.object(self.kpi_admin_module, "_sync_tender_before_analysis_job", sync_mock):
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
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client), patch.object(self.kpi_admin_module, "_sync_tender_before_analysis_job", sync_mock):
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
                "next_best_actions": [
                    {
                        "code": "protect_submission_corridor",
                        "title": "Protect the submission corridor",
                        "priority": "now",
                        "rationale": "The tender is leaning toward the submission path.",
                        "expected_impact": "Keep the tender on the shortest path to submission.",
                        "confidence": 0.81,
                        "drivers": ["Projected path: S6 -> S8 -> S9"],
                    }
                ],
                "analysis_metadata": {
                    "rollout_policy": "full",
                    "markov_rollout_enabled": True,
                    "calibrated_forecast_enabled": True,
                    "forecast_engine_active": "markov_full_lifecycle_v1",
                    "forecast_signal_type": "calibrated",
                    "forecast_engine_candidates": ["markov_full_lifecycle_v1", "heuristic_rule_v1"],
                    "markov_model_active": True,
                    "markov_model_version": "markov-full-lifecycle-v1",
                    "markov_phase_scope": ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"],
                    "markov_reliable_phase_scope": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"],
                    "semantic_priority": ["A1", "A4"],
                    "canonical_source_types": ["observed", "inferred", "reconstructed"],
                    "shadow_kpis": ["A1", "A4"],
                    "markov_state_scope": ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"],
                    "markov_absorbing_states": ["S11", "S12", "S13"],
                    "markov_source_mix": {"observed": 4, "reconstructed": 1},
                    "markov_bundle_kind": "full_journey",
                    "markov_full_journey_enabled": True,
                    "markov_coverage_ratio": 0.56,
                    "markov_projected_path": ["S6", "S8", "S9"],
                    "markov_backtest_version": "markov-backtest-v1",
                    "markov_backtest_sample_count": 8,
                    "markov_backtest_submission_accuracy": 0.75,
                    "markov_backtest_calibration_gap": 0.19,
                    "forecast_driver_kpis": ["A1", "A4"],
                    "forecast_driver_scores": {"A1": 72.5, "A4": 68.0},
                    "forecast_primary_action_code": "protect_submission_corridor",
                    "forecast_primary_action_confidence": 0.81,
                    "forecast_decision_bundle_version": "forecast-decision-support-v1",
                    "scored_kpis": ["A1", "A4"],
                },
            })

        mock_client.get_tender_forecast = rich_forecast
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/forecast")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["upstream_status_code"], 200)
        self.assertEqual(payload["scenarios"][0]["name"], "submit_on_time")
        self.assertEqual(payload["scenarios"][0]["drivers"], ["Q remains stable"])
        self.assertEqual(payload["analysis_metadata"]["forecast_signal_type"], "calibrated")
        self.assertEqual(payload["analysis_metadata"]["forecast_engine_active"], "markov_full_lifecycle_v1")
        self.assertEqual(payload["analysis_metadata"]["markov_model_version"], "markov-full-lifecycle-v1")
        self.assertEqual(payload["analysis_metadata"]["markov_bundle_kind"], "full_journey")
        self.assertTrue(payload["analysis_metadata"]["markov_full_journey_enabled"])
        self.assertEqual(payload["analysis_metadata"]["markov_projected_path"], ["S6", "S8", "S9"])
        self.assertEqual(payload["analysis_metadata"]["forecast_driver_scores"], {"A1": 72.5, "A4": 68.0})
        self.assertEqual(payload["analysis_metadata"]["forecast_primary_action_code"], "protect_submission_corridor")
        self.assertEqual(payload["analysis_metadata"]["forecast_decision_bundle_version"], "forecast-decision-support-v1")
        self.assertTrue(payload["analysis_metadata"]["markov_rollout_enabled"])
        self.assertEqual(payload["analysis_metadata"]["markov_source_mix"], {"observed": 4, "reconstructed": 1})
        self.assertEqual(payload["next_best_actions"][0]["code"], "protect_submission_corridor")

    def test_portfolio_intelligence_query_preserves_rich_payload(self) -> None:
        mock_client = _MockKpiClient()

        async def rich_intelligence() -> KpiClientResult:
            return KpiClientResult(True, 200, {
                "status": "not_ready",
                "generated_at": "2026-03-20T09:30:00Z",
                "phase_hotspots": [
                    {
                        "phase": "S6",
                        "count": 3,
                        "summary": "3 tenders are concentrated in Rework / Clarifications.",
                    }
                ],
                "risk_hotspots": [
                    {
                        "code": "A4",
                        "count": 2,
                        "severity": "critical",
                        "summary": "Compliance risk remains a dominant cross-tender blocker.",
                    }
                ],
                "outcome_trends": {"S11": 1, "S12": 1, "S13": 2},
                "watchlist": [
                    {
                        "external_tender_id": "TEN-RED",
                        "title": "Critical tender",
                        "analytical_phase": "S8",
                        "health": "red",
                        "summary": "Compliance gate remains blocked.",
                    }
                ],
                "notes": ["Primary hotspot is A4 with 2 mirrored tenders."],
            })

        mock_client.get_portfolio_intelligence = rich_intelligence
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/portfolio/intelligence")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["phase_hotspots"][0]["phase"], "S6")
        self.assertEqual(payload["risk_hotspots"][0]["code"], "A4")
        self.assertEqual(payload["watchlist"][0]["external_tender_id"], "TEN-RED")
        self.assertEqual(payload["outcome_trends"], {"S11": 1, "S12": 1, "S13": 2})

    def test_latest_analysis_job_falls_back_to_degraded_state(self) -> None:
        mock_client = _MockKpiClient()

        async def failing_latest_job(external_tender_id: str) -> KpiClientResult:
            return KpiClientResult(False, None, {}, "KPI service timeout")

        mock_client.get_latest_analysis_job = failing_latest_job
        with patch.object(self.kpi_admin_module, "KpiReasonEngineClient", return_value=mock_client):
            response = self.client.get("/admin/kpi/tenders/12/analysis-jobs/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["job_status"], "degraded")
        self.assertEqual(payload["error_message"], "KPI service timeout")


if __name__ == "__main__":
    unittest.main()
