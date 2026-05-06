"""Tests for the Wave-3 rehearsal_summary enrichment (PR-10).

Covers the pure helpers in :mod:`app.intelligence.rehearsal_summary`
and the endpoint wiring in :mod:`app.api.intelligence` + KPI forecast
enrichment in :mod:`app.api.kpi_admin`.

DB round-trips are faked via ``unittest.mock.patch.object`` on the
three internal fetch helpers so tests focus on mapping logic rather
than SQL construction.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
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
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


_MODELS = load_models_test_module()
_SUMMARY = load_service_test_module("app.intelligence.rehearsal_summary")
_API_MODULE = load_service_test_module("app.api.intelligence")


RehearsalRun = _MODELS.RehearsalRun
RehearsalRunStatus = _MODELS.RehearsalRunStatus
RehearsalMode = _MODELS.RehearsalMode


def _make_run(
    *,
    run_id: int = 1,
    tender_id: int = 10,
    proposal_id: int = 20,
    overall_score: float | None = 72.5,
    persona_divergence: float | None = 0.28,
    health_projection: str | None = "amber",
    completed_at: datetime | None = None,
) -> RehearsalRun:
    run = RehearsalRun(
        tender_id=tender_id,
        proposal_id=proposal_id,
        mode=RehearsalMode.FULL,
        status=RehearsalRunStatus.COMPLETED,
        context_snapshot_json={},
    )
    run.id = run_id
    run.overall_score = overall_score
    run.persona_divergence = persona_divergence
    run.health_projection = health_projection
    run.completed_at = completed_at or datetime(2026, 4, 17, 18, 40, tzinfo=timezone.utc)
    return run


class EmptySummaryTests(unittest.TestCase):
    def test_shape_matches_contract(self):
        payload = _SUMMARY.empty_rehearsal_summary()
        expected_keys = {
            "run_id",
            "last_rehearsal_at",
            "overall_score",
            "persona_divergence",
            "blocking_findings",
            "high_severity_rework_suggestions",
            "health_projection",
            "version",
        }
        self.assertEqual(set(payload), expected_keys)
        self.assertEqual(payload["blocking_findings"], 0)
        self.assertEqual(payload["high_severity_rework_suggestions"], 0)
        self.assertEqual(payload["version"], "tw-rehearsal-v1")


class BuildSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_completed_run_returns_none(self):
        with patch.object(_SUMMARY, "_latest_completed_run", AsyncMock(return_value=None)):
            result = await _SUMMARY.build_rehearsal_summary(db=object(), tender_id=10)
        self.assertIsNone(result)

    async def test_maps_run_fields_into_summary(self):
        run = _make_run()
        with (
            patch.object(_SUMMARY, "_latest_completed_run", AsyncMock(return_value=run)),
            patch.object(_SUMMARY, "_blocking_findings_count", AsyncMock(return_value=3)),
            patch.object(
                _SUMMARY,
                "_high_severity_rework_count",
                AsyncMock(return_value=2),
            ),
        ):
            result = await _SUMMARY.build_rehearsal_summary(db=object(), tender_id=10)

        self.assertIsNotNone(result)
        self.assertEqual(result["run_id"], 1)
        self.assertEqual(result["tender_id"], 10)
        self.assertEqual(result["proposal_id"], 20)
        self.assertEqual(result["overall_score"], 72.5)
        self.assertEqual(result["persona_divergence"], 0.28)
        self.assertEqual(result["blocking_findings"], 3)
        self.assertEqual(result["high_severity_rework_suggestions"], 2)
        self.assertEqual(result["health_projection"], "amber")
        self.assertEqual(result["last_rehearsal_at"], run.completed_at.isoformat())
        self.assertEqual(result["version"], "tw-rehearsal-v1")

    async def test_null_metrics_preserve_none(self):
        run = _make_run(
            overall_score=None,
            persona_divergence=None,
            health_projection=None,
        )
        with (
            patch.object(_SUMMARY, "_latest_completed_run", AsyncMock(return_value=run)),
            patch.object(_SUMMARY, "_blocking_findings_count", AsyncMock(return_value=0)),
            patch.object(
                _SUMMARY,
                "_high_severity_rework_count",
                AsyncMock(return_value=0),
            ),
        ):
            result = await _SUMMARY.build_rehearsal_summary(db=object(), tender_id=10)

        self.assertIsNone(result["overall_score"])
        self.assertIsNone(result["persona_divergence"])
        self.assertIsNone(result["health_projection"])
        self.assertEqual(result["blocking_findings"], 0)

    async def test_proposal_id_is_forwarded_to_lookup(self):
        mock_lookup = AsyncMock(return_value=None)
        with patch.object(_SUMMARY, "_latest_completed_run", mock_lookup):
            await _SUMMARY.build_rehearsal_summary(db="db-sentinel", tender_id=10, proposal_id=42)
        mock_lookup.assert_awaited_once_with("db-sentinel", tender_id=10, proposal_id=42)


class ApiWiringTests(unittest.TestCase):
    def test_rehearsal_summary_route_registered(self):
        paths = {route.path for route in _API_MODULE.router.routes}
        self.assertIn("/tenders/{tender_id}/rehearsal-summary", paths)

    def test_route_is_get(self):
        for route in _API_MODULE.router.routes:
            if route.path == "/tenders/{tender_id}/rehearsal-summary":
                self.assertIn("GET", route.methods or set())
                break
        else:
            self.fail("rehearsal-summary route missing")


class KpiForecastEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_handler_attaches_rehearsal_summary_block(self):
        kpi_admin = load_service_test_module("app.api.kpi_admin")

        async def fake_get_tender_forecast(self, external_tender_id):
            return kpi_admin.KpiClientResult(
                delivered=True,
                status_code=200,
                response_json={"scenarios": [], "next_best_actions": []},
            )

        summary_payload = {
            "run_id": 7,
            "tender_id": 10,
            "proposal_id": 3,
            "last_rehearsal_at": "2026-04-17T18:40:00+00:00",
            "overall_score": 71.0,
            "persona_divergence": 0.21,
            "blocking_findings": 2,
            "high_severity_rework_suggestions": 1,
            "health_projection": "amber",
            "version": "tw-rehearsal-v1",
        }

        admin_user = kpi_admin.UserResponse(
            id=1,
            email="admin@example.org",
            name="admin",
            role="admin",
        )

        with (
            patch.object(
                kpi_admin.KpiReasonEngineClient,
                "get_tender_forecast",
                fake_get_tender_forecast,
            ),
            patch.object(
                kpi_admin,
                "build_rehearsal_summary",
                AsyncMock(return_value=summary_payload),
            ),
            patch.object(kpi_admin, "_audit_admin_event", lambda **_: None),
            patch.object(kpi_admin.settings, "rehearsal_summary_enabled", True),
        ):
            result = await kpi_admin.get_kpi_tender_forecast(
                tender_id=10,
                current_user=admin_user,
                db=object(),
            )

        self.assertIn("rehearsal_summary", result)
        self.assertEqual(result["rehearsal_summary"]["run_id"], 7)
        self.assertEqual(result["rehearsal_summary"]["health_projection"], "amber")

    async def test_handler_falls_back_to_empty_summary_when_none(self):
        kpi_admin = load_service_test_module("app.api.kpi_admin")

        async def fake_get_tender_forecast(self, external_tender_id):
            return kpi_admin.KpiClientResult(
                delivered=True,
                status_code=200,
                response_json={"scenarios": [], "next_best_actions": []},
            )

        admin_user = kpi_admin.UserResponse(
            id=1,
            email="admin@example.org",
            name="admin",
            role="admin",
        )

        with (
            patch.object(
                kpi_admin.KpiReasonEngineClient,
                "get_tender_forecast",
                fake_get_tender_forecast,
            ),
            patch.object(
                kpi_admin,
                "build_rehearsal_summary",
                AsyncMock(return_value=None),
            ),
            patch.object(kpi_admin, "_audit_admin_event", lambda **_: None),
            patch.object(kpi_admin.settings, "rehearsal_summary_enabled", True),
        ):
            result = await kpi_admin.get_kpi_tender_forecast(
                tender_id=10,
                current_user=admin_user,
                db=object(),
            )

        self.assertIn("rehearsal_summary", result)
        self.assertEqual(result["rehearsal_summary"]["run_id"], None)
        self.assertEqual(result["rehearsal_summary"]["blocking_findings"], 0)
        self.assertEqual(result["rehearsal_summary"]["tender_id"], 10)

    async def test_handler_omits_rehearsal_summary_when_flag_disabled(self):
        kpi_admin = load_service_test_module("app.api.kpi_admin")

        async def fake_get_tender_forecast(self, external_tender_id):
            return kpi_admin.KpiClientResult(
                delivered=True,
                status_code=200,
                response_json={"scenarios": [], "next_best_actions": []},
            )

        admin_user = kpi_admin.UserResponse(
            id=1,
            email="admin@example.org",
            name="admin",
            role="admin",
        )

        build_mock = AsyncMock()
        with (
            patch.object(
                kpi_admin.KpiReasonEngineClient,
                "get_tender_forecast",
                fake_get_tender_forecast,
            ),
            patch.object(kpi_admin, "build_rehearsal_summary", build_mock),
            patch.object(kpi_admin, "_audit_admin_event", lambda **_: None),
            patch.object(kpi_admin.settings, "rehearsal_summary_enabled", False),
        ):
            result = await kpi_admin.get_kpi_tender_forecast(
                tender_id=10,
                current_user=admin_user,
                db=object(),
            )

        self.assertNotIn("rehearsal_summary", result)
        build_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
