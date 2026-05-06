"""Tests for the Wave-3 rehearsal_converter (PR-09).

Covers:

- ``accept_recommendation`` — rejects non-PROPOSED / non-convertible
  scopes, requires requirement→section linkage, creates ``ReworkAction``
  and links it back on the happy path.
- ``dismiss_recommendation`` — rejects non-PROPOSED, appends the
  dismissal reason to the rationale.
- API module wiring — accept/dismiss endpoints are registered.

The converter is unit-tested with an in-memory fake ``AsyncSession``
that exposes just the surface the converter touches
(``get``, ``add``, ``flush``) and a monkey-patched
``ensure_contribution_for_section``.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

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
_CONVERTER = load_service_test_module("app.intelligence.rehearsal_converter")
_API_MODULE = load_service_test_module("app.api.intelligence")


RehearsalRecommendation = _MODELS.RehearsalRecommendation
RehearsalRecommendationStatus = _MODELS.RehearsalRecommendationStatus
ReworkAction = _MODELS.ReworkAction
ReworkStatus = _MODELS.ReworkStatus
ProposalSection = _MODELS.ProposalSection
TenderRequirement = _MODELS.TenderRequirement
ContributionUnit = _MODELS.ContributionUnit


class _FakeSession:
    """Minimal async-compatible session stub."""

    def __init__(self, lookups: dict[tuple[type, int], Any]) -> None:
        self._lookups = lookups
        self.added: list[Any] = []
        self.flush_calls = 0

    async def get(self, model, pk):
        return self._lookups.get((model, pk))

    def add(self, obj):
        # mimic PK assignment that the ORM would do on flush
        if isinstance(obj, ReworkAction) and getattr(obj, "id", None) is None:
            obj.id = 4242
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1


def _make_recommendation(
    *,
    rec_id: int = 1,
    run_id: int = 1,
    scope_type: str = "proposal_section",
    scope_id: str = "10",
    status=RehearsalRecommendationStatus.PROPOSED,
    rationale: str = "motivazione",
    severity: str = "high",
    is_blocking: bool = True,
    source_persona_id: str = "compliance_officer",
) -> RehearsalRecommendation:
    rec = RehearsalRecommendation(
        rehearsal_run_id=run_id,
        scope_type=scope_type,
        scope_id=scope_id,
        severity=severity,
        is_blocking=is_blocking,
        rationale=rationale,
        suggested_owner_role="compliance",
        source_persona_id=source_persona_id,
        status=status,
    )
    rec.id = rec_id
    rec.linked_rework_action_id = None
    return rec


class AcceptRecommendationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_proposed(self):
        rec = _make_recommendation(status=RehearsalRecommendationStatus.ACCEPTED)
        session = _FakeSession({})
        with self.assertRaises(ValueError):
            await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=None,
            )

    async def test_rejects_non_convertible_scope(self):
        rec = _make_recommendation(scope_type="gate", scope_id="failed_gates")
        session = _FakeSession({})
        with self.assertRaises(ValueError):
            await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=None,
            )

    async def test_rejects_non_numeric_scope_id(self):
        rec = _make_recommendation(scope_id="not-a-number")
        session = _FakeSession({})
        with self.assertRaises(ValueError):
            await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=None,
            )

    async def test_requirement_without_section_is_rejected(self):
        requirement = TenderRequirement(
            tender_id=1,
            requirement_text="req",
        )
        requirement.id = 7
        requirement.proposal_section_id = None

        rec = _make_recommendation(scope_type="requirement", scope_id="7")
        session = _FakeSession({(TenderRequirement, 7): requirement})

        with self.assertRaises(ValueError):
            await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=None,
            )

    async def test_requirement_from_wrong_tender_is_rejected(self):
        requirement = TenderRequirement(
            tender_id=999,
            requirement_text="req",
        )
        requirement.id = 7
        requirement.proposal_section_id = 5

        rec = _make_recommendation(scope_type="requirement", scope_id="7")
        session = _FakeSession({(TenderRequirement, 7): requirement})

        with self.assertRaises(ValueError):
            await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=None,
            )

    async def test_happy_path_section_scope_creates_rework_and_links(self):
        section = ProposalSection(title="Sez", status=None)
        section.id = 10
        contribution = ContributionUnit(title="c", tender_id=1)
        contribution.id = 33
        contribution.owner_user_id = 99

        rec = _make_recommendation(scope_type="proposal_section", scope_id="10")
        session = _FakeSession({(ProposalSection, 10): section})

        async def fake_ensure(db, *, tender_id, section, actor_id):
            self.assertIs(db, session)
            self.assertEqual(tender_id, 1)
            self.assertIs(section, session._lookups[(ProposalSection, 10)])
            return contribution

        with patch.object(_CONVERTER, "ensure_contribution_for_section", fake_ensure):
            rework = await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=42,
            )

        self.assertIsInstance(rework, ReworkAction)
        self.assertEqual(rework.contribution_unit_id, 33)
        self.assertEqual(rework.requested_by, 42)
        self.assertEqual(rework.assigned_to_user_id, 99)
        self.assertEqual(rework.severity, "high")
        self.assertTrue(rework.is_blocking)
        self.assertEqual(rework.reason, "motivazione")
        self.assertEqual(rework.status, ReworkStatus.OPEN)

        self.assertEqual(rec.status, RehearsalRecommendationStatus.ACCEPTED)
        self.assertEqual(rec.linked_rework_action_id, rework.id)

    async def test_overrides_applied(self):
        section = ProposalSection(title="Sez", status=None)
        section.id = 10
        contribution = ContributionUnit(title="c", tender_id=1)
        contribution.id = 33
        contribution.owner_user_id = 99

        rec = _make_recommendation(
            scope_type="proposal_section",
            scope_id="10",
            severity="medium",
            is_blocking=False,
        )
        session = _FakeSession({(ProposalSection, 10): section})

        overrides = _CONVERTER.AcceptOverrides(
            assigned_to_user_id=7,
            due_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            severity="low",
            is_blocking=True,
            notes="custom reason",
        )

        async def fake_ensure(db, *, tender_id, section, actor_id):
            return contribution

        with patch.object(_CONVERTER, "ensure_contribution_for_section", fake_ensure):
            rework = await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=42,
                overrides=overrides,
            )

        self.assertEqual(rework.assigned_to_user_id, 7)
        self.assertEqual(rework.due_at, overrides.due_at)
        self.assertEqual(rework.severity, "low")
        self.assertTrue(rework.is_blocking)
        self.assertEqual(rework.reason, "custom reason")

    async def test_requirement_scope_resolves_section(self):
        requirement = TenderRequirement(tender_id=1, requirement_text="req")
        requirement.id = 7
        requirement.proposal_section_id = 10

        section = ProposalSection(title="Sez", status=None)
        section.id = 10
        contribution = ContributionUnit(title="c", tender_id=1)
        contribution.id = 55
        contribution.owner_user_id = None

        rec = _make_recommendation(scope_type="requirement", scope_id="7")
        session = _FakeSession(
            {
                (TenderRequirement, 7): requirement,
                (ProposalSection, 10): section,
            }
        )

        async def fake_ensure(db, *, tender_id, section, actor_id):
            self.assertEqual(section.id, 10)
            return contribution

        with patch.object(_CONVERTER, "ensure_contribution_for_section", fake_ensure):
            rework = await _CONVERTER.accept_recommendation(
                session,
                recommendation=rec,
                tender_id=1,
                actor_id=1,
            )

        self.assertEqual(rework.contribution_unit_id, 55)
        self.assertEqual(rec.linked_rework_action_id, rework.id)


class DismissRecommendationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_proposed(self):
        rec = _make_recommendation(status=RehearsalRecommendationStatus.DISMISSED)
        session = _FakeSession({})
        with self.assertRaises(ValueError):
            await _CONVERTER.dismiss_recommendation(
                session,
                recommendation=rec,
                actor_id=1,
            )

    async def test_flips_status_without_reason(self):
        rec = _make_recommendation()
        session = _FakeSession({})
        await _CONVERTER.dismiss_recommendation(
            session,
            recommendation=rec,
            actor_id=1,
        )
        self.assertEqual(rec.status, RehearsalRecommendationStatus.DISMISSED)
        self.assertEqual(rec.rationale, "motivazione")

    async def test_appends_reason_when_provided(self):
        rec = _make_recommendation(rationale="original")
        session = _FakeSession({})
        await _CONVERTER.dismiss_recommendation(
            session,
            recommendation=rec,
            actor_id=1,
            reason="falso positivo",
        )
        self.assertEqual(rec.status, RehearsalRecommendationStatus.DISMISSED)
        self.assertIn("[dismissed] falso positivo", rec.rationale)
        self.assertTrue(rec.rationale.startswith("original"))


class ApiWiringTests(unittest.TestCase):
    def test_accept_dismiss_routes_registered(self):
        paths = {route.path for route in _API_MODULE.router.routes}
        self.assertIn(
            "/rehearsals/{run_id}/recommendations/{recommendation_id}/accept",
            paths,
        )
        self.assertIn(
            "/rehearsals/{run_id}/recommendations/{recommendation_id}/dismiss",
            paths,
        )

    def test_accept_and_dismiss_are_post(self):
        for route in _API_MODULE.router.routes:
            if route.path.endswith("/accept") or route.path.endswith("/dismiss"):
                self.assertIn("POST", route.methods or set())


if __name__ == "__main__":
    unittest.main()
