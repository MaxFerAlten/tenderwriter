"""Wiring tests for the rehearsal endpoints + Celery enqueue helper.

These tests verify:

- :mod:`app.api.intelligence` exposes the rehearsal router paths.
- The ``_enqueue_rehearsal`` module-level helper actually dispatches via
  Celery's ``.delay()`` — so the POST handler can be monkey-patched in
  higher-level tests without going through Redis.
- Module-level singleton setters clear the cached instances so tests
  can swap fakes.

No DB traffic: imports go through :mod:`test_module_loaders`.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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
_API_MODULE = load_service_test_module("app.api.intelligence")


class RouterPathsTests(unittest.TestCase):
    def test_rehearsal_routes_registered(self):
        paths = {route.path for route in _API_MODULE.router.routes}
        self.assertIn("/rehearsals", paths)
        self.assertIn("/rehearsals/{run_id}", paths)

    def test_create_rehearsal_exists_as_post(self):
        matching = [r for r in _API_MODULE.router.routes if r.path == "/rehearsals"]
        methods = {m for r in matching for m in (r.methods or set())}
        self.assertIn("POST", methods)
        self.assertIn("GET", methods)


class EnqueueHelperTests(unittest.TestCase):
    def test_enqueue_rehearsal_dispatches_via_celery_delay(self):
        fake_task = MagicMock()
        fake_task.delay = MagicMock()
        fake_tasks_module = MagicMock()
        fake_tasks_module.run_rehearsal_task = fake_task

        with patch.dict("sys.modules", {"app.tasks": fake_tasks_module}):
            _API_MODULE._enqueue_rehearsal(123)

        fake_task.delay.assert_called_once_with(123)


class TestingHooksTests(unittest.TestCase):
    def test_set_tool_registry_for_testing_resets_agent_and_rehearsal(self):
        _API_MODULE._agent = object()
        _API_MODULE._rehearsal_service = object()
        _API_MODULE.set_tool_registry_for_testing(None)
        self.assertIsNone(_API_MODULE._registry)
        self.assertIsNone(_API_MODULE._agent)
        self.assertIsNone(_API_MODULE._rehearsal_service)

    def test_set_rehearsal_service_for_testing_swaps_instance(self):
        sentinel = object()
        _API_MODULE.set_rehearsal_service_for_testing(sentinel)
        self.assertIs(_API_MODULE._rehearsal_service, sentinel)
        _API_MODULE.set_rehearsal_service_for_testing(None)
        self.assertIsNone(_API_MODULE._rehearsal_service)


class SerializerTests(unittest.TestCase):
    def test_persona_result_to_response_validates_findings(self):
        row = MagicMock()
        row.persona_id = "compliance_officer"
        row.display_name = "Compliance"
        row.reviewer_type = "compliance_officer"
        row.score = 72.5
        row.findings_json = [
            {
                "category": "coverage_gap",
                "severity": "high",
                "summary": "missing doc",
                "scope_type": "requirement",
                "scope_id": "R-1",
                "supporting_refs": [],
            }
        ]
        row.questions_json = [{"question": "Dove si trova il documento?"}]
        row.metrics_json = {"coverage_gaps_high": 1}

        response = _API_MODULE._persona_result_to_response(row)
        self.assertEqual(response.persona_id, "compliance_officer")
        self.assertEqual(response.score, 72.5)
        self.assertEqual(len(response.findings), 1)
        self.assertEqual(response.findings[0].scope_id, "R-1")
        self.assertEqual(len(response.questions), 1)
        self.assertEqual(response.metrics, {"coverage_gaps_high": 1})

    def test_recommendation_to_response_serialises_enum_status(self):
        from app.models import RehearsalRecommendationStatus

        row = MagicMock()
        row.id = 7
        row.scope_type = "requirement"
        row.scope_id = "R-7"
        row.severity = "high"
        row.is_blocking = True
        row.rationale = "motivazione"
        row.suggested_owner_role = "bid_manager"
        row.source_persona_id = "formalista_amministrativo"
        row.status = RehearsalRecommendationStatus.PROPOSED
        row.linked_rework_action_id = None

        response = _API_MODULE._recommendation_to_response(row)
        self.assertEqual(response.id, 7)
        self.assertTrue(response.is_blocking)
        self.assertEqual(response.status, "proposed")
        self.assertIsNone(response.linked_rework_action_id)

    def test_run_to_response_handles_empty_children(self):
        from app.models import RehearsalMode, RehearsalRunStatus

        run = MagicMock()
        run.id = 1
        run.tender_id = 10
        run.proposal_id = 20
        run.mode = RehearsalMode.FULL
        run.status = RehearsalRunStatus.PENDING
        run.overall_score = None
        run.health_projection = None
        run.persona_divergence = None
        run.started_at = None
        run.completed_at = None
        run.persona_results = []
        run.recommendations = []
        run.error_message = None
        run.version = "tw-rehearsal-v1"

        response = _API_MODULE._rehearsal_run_to_response(run)
        self.assertEqual(response.id, 1)
        self.assertEqual(response.status, "pending")
        self.assertEqual(response.mode, "full")
        self.assertEqual(response.persona_results, [])
        self.assertEqual(response.recommendations, [])


def _build_user(role: str = "user") -> object:
    user = MagicMock()
    user.id = 1
    user.email = "user@example.org"
    user.name = "user"
    user.role = role
    return user


def _build_request(*, tender_id: int = 10, proposal_id: int = 20):
    payload = MagicMock()
    payload.tender_id = tender_id
    payload.proposal_id = proposal_id
    payload.proposal_section_ids = []
    payload.persona_ids = []
    payload.mode = "full"
    payload.include_forecast_context = True
    return payload


class CreateRehearsalStatusGuardTests(unittest.TestCase):
    def _run_with_status(self, status):
        tender = MagicMock()
        tender.status = status

        db = MagicMock()
        db.get = AsyncMock(return_value=tender)

        with (
            patch.object(
                _API_MODULE,
                "check_tender_access",
                AsyncMock(return_value=None),
            ),
            patch.object(
                _API_MODULE,
                "get_rehearsal_service",
                lambda: (_ for _ in ()).throw(
                    AssertionError("service must not be created when blocked")
                ),
            ),
        ):
            with self.assertRaises(_API_MODULE.HTTPException) as ctx:
                asyncio.run(
                    _API_MODULE.create_rehearsal_run(
                        payload=_build_request(),
                        current_user=_build_user(role="admin"),
                        db=db,
                    )
                )
        return ctx.exception

    def test_blocked_when_tender_submitted(self):
        from app.models import TenderStatus

        exc = self._run_with_status(TenderStatus.SUBMITTED)
        self.assertEqual(exc.status_code, 409)
        self.assertIn("submission", exc.detail.lower())

    def test_blocked_when_tender_won(self):
        from app.models import TenderStatus

        exc = self._run_with_status(TenderStatus.WON)
        self.assertEqual(exc.status_code, 409)

    def test_blocked_when_tender_lost(self):
        from app.models import TenderStatus

        exc = self._run_with_status(TenderStatus.LOST)
        self.assertEqual(exc.status_code, 409)

    def test_blocked_when_tender_cancelled(self):
        from app.models import TenderStatus

        exc = self._run_with_status(TenderStatus.CANCELLED)
        self.assertEqual(exc.status_code, 409)

    def test_missing_tender_returns_404(self):
        db = MagicMock()
        db.get = AsyncMock(return_value=None)

        with (
            patch.object(
                _API_MODULE,
                "check_tender_access",
                AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(_API_MODULE.HTTPException) as ctx:
                asyncio.run(
                    _API_MODULE.create_rehearsal_run(
                        payload=_build_request(),
                        current_user=_build_user(role="admin"),
                        db=db,
                    )
                )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_active_status_passes_guard_and_hits_proposal_lookup(self):
        """Guard is unconditional on role, but must not false-positive for DRAFT.

        We pass DRAFT + missing proposal → expect 404 on proposal, proving
        the status guard fell through.
        """
        from app.models import TenderStatus

        tender = MagicMock()
        tender.status = TenderStatus.DRAFT

        db = MagicMock()
        db.get = AsyncMock(side_effect=[tender, None])

        with (
            patch.object(
                _API_MODULE,
                "check_tender_access",
                AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(_API_MODULE.HTTPException) as ctx:
                asyncio.run(
                    _API_MODULE.create_rehearsal_run(
                        payload=_build_request(),
                        current_user=_build_user(role="user"),
                        db=db,
                    )
                )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("proposal", ctx.exception.detail.lower())


class RecommendationAdminGateTests(unittest.TestCase):
    def test_accept_requires_admin(self):
        db = MagicMock()
        with self.assertRaises(_API_MODULE.HTTPException) as ctx:
            asyncio.run(
                _API_MODULE.accept_rehearsal_recommendation(
                    run_id=1,
                    recommendation_id=2,
                    payload=None,
                    current_user=_build_user(role="user"),
                    db=db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("admin", ctx.exception.detail.lower())

    def test_dismiss_requires_admin(self):
        db = MagicMock()
        with self.assertRaises(_API_MODULE.HTTPException) as ctx:
            asyncio.run(
                _API_MODULE.dismiss_rehearsal_recommendation(
                    run_id=1,
                    recommendation_id=2,
                    payload=None,
                    current_user=_build_user(role="user"),
                    db=db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_require_admin_helper_passes_for_admin(self):
        # Sanity: helper does not raise for admin role
        _API_MODULE._require_admin(_build_user(role="admin"))


if __name__ == "__main__":
    unittest.main()
