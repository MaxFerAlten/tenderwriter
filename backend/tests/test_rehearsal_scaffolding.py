"""Unit tests for the Wave-3 rehearsal scaffolding.

Covers:

- persona catalog invariants (weight sum, strictness/risk bounds,
  version field, serialisation round-trip);
- :func:`resolve_personas` default + explicit behaviour;
- Pydantic contracts (request/response shapes, rejection of bad
  payloads);
- SQLAlchemy models are importable + exported from :mod:`app.models`
  with the expected ``__tablename__`` and enum values.

These tests do not hit the database; they rely on
:mod:`test_module_loaders` to load service modules with a mocked
async engine, exactly like the PR-05 / PR-06 suites.
"""

from __future__ import annotations

import os
import unittest

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
_PERSONAS_MODULE = load_service_test_module("app.intelligence.personas")
_CATALOG_MODULE = load_service_test_module("app.intelligence.persona_catalog")
_SCHEMAS_MODULE = load_service_test_module("app.intelligence.schemas")


class PersonaCatalogInvariantsTests(unittest.TestCase):
    def test_catalog_contains_five_default_personas(self):
        catalog = _CATALOG_MODULE.PERSONA_CATALOG
        self.assertEqual(len(catalog), 5)
        self.assertEqual(
            set(catalog),
            {
                "formalista_amministrativo",
                "valutatore_tecnico",
                "compliance_officer",
                "economico_finanziario",
                "rup_simulato",
            },
        )

    def test_default_ids_match_catalog_keys(self):
        self.assertEqual(
            set(_CATALOG_MODULE.DEFAULT_PERSONA_IDS),
            set(_CATALOG_MODULE.PERSONA_CATALOG),
        )

    def test_persona_invariants_hold_for_every_entry(self):
        for persona in _CATALOG_MODULE.PERSONA_CATALOG.values():
            with self.subTest(persona_id=persona.persona_id):
                self.assertEqual(persona.version, _PERSONAS_MODULE.PERSONA_CATALOG_VERSION)
                self.assertEqual(persona.persona_id, persona.reviewer_type)
                self.assertGreaterEqual(persona.strictness, 1)
                self.assertLessEqual(persona.strictness, 5)
                self.assertGreaterEqual(persona.risk_aversion, 1)
                self.assertLessEqual(persona.risk_aversion, 5)
                self.assertGreater(len(persona.focus_domains), 0)
                self.assertAlmostEqual(
                    sum(persona.scoring_weights.values()),
                    1.0,
                    delta=0.01,
                )

    def test_persona_as_dict_is_json_safe_round_trip(self):
        import json

        persona = _CATALOG_MODULE.PERSONA_CATALOG["valutatore_tecnico"]
        payload = _PERSONAS_MODULE.persona_as_dict(persona)
        encoded = json.dumps(payload, sort_keys=True)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["persona_id"], "valutatore_tecnico")
        self.assertEqual(decoded["reviewer_type"], "valutatore_tecnico")
        self.assertIsInstance(decoded["focus_domains"], list)
        self.assertIsInstance(decoded["scoring_weights"], dict)
        self.assertEqual(decoded["version"], _PERSONAS_MODULE.PERSONA_CATALOG_VERSION)

    def test_validate_persona_rejects_bad_weights(self):
        persona = _PERSONAS_MODULE.ReviewerPersona(
            persona_id="broken_sum",
            display_name="Broken",
            reviewer_type="formalista_amministrativo",
            focus_domains=("amministrativo",),
            strictness=3,
            risk_aversion=3,
            scoring_weights={"a": 0.5, "b": 0.2},
        )
        with self.assertRaises(ValueError):
            _PERSONAS_MODULE._validate_persona(persona)

    def test_validate_persona_rejects_out_of_range_strictness(self):
        persona = _PERSONAS_MODULE.ReviewerPersona(
            persona_id="too_strict",
            display_name="Too strict",
            reviewer_type="formalista_amministrativo",
            focus_domains=("amministrativo",),
            strictness=6,
            risk_aversion=3,
            scoring_weights={"a": 1.0},
        )
        with self.assertRaises(ValueError):
            _PERSONAS_MODULE._validate_persona(persona)


class ResolvePersonasTests(unittest.TestCase):
    def test_empty_input_returns_default_catalog_order(self):
        resolved = _CATALOG_MODULE.resolve_personas([])
        self.assertEqual(len(resolved), 5)
        self.assertEqual(
            [p.persona_id for p in resolved],
            list(_CATALOG_MODULE.DEFAULT_PERSONA_IDS),
        )

    def test_none_input_returns_default_catalog(self):
        resolved = _CATALOG_MODULE.resolve_personas(None)
        self.assertEqual(len(resolved), 5)

    def test_explicit_ids_preserve_order(self):
        resolved = _CATALOG_MODULE.resolve_personas(["compliance_officer", "rup_simulato"])
        self.assertEqual(
            [p.persona_id for p in resolved],
            ["compliance_officer", "rup_simulato"],
        )

    def test_unknown_persona_id_raises(self):
        with self.assertRaises(KeyError):
            _CATALOG_MODULE.resolve_personas(["inesistente"])


class RehearsalPydanticContractsTests(unittest.TestCase):
    def test_create_request_accepts_minimum_payload(self):
        request = _SCHEMAS_MODULE.RehearsalCreateRequest(
            tender_id=1,
            proposal_id=2,
        )
        self.assertEqual(request.mode, "full")
        self.assertTrue(request.include_forecast_context)
        self.assertEqual(request.proposal_section_ids, [])
        self.assertEqual(request.persona_ids, [])

    def test_create_request_rejects_bad_mode(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            _SCHEMAS_MODULE.RehearsalCreateRequest(
                tender_id=1,
                proposal_id=2,
                mode="regression",
            )

    def test_create_request_rejects_extra_fields(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            _SCHEMAS_MODULE.RehearsalCreateRequest(
                tender_id=1,
                proposal_id=2,
                surprise="reject",
            )

    def test_create_request_rejects_non_positive_ids(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            _SCHEMAS_MODULE.RehearsalCreateRequest(tender_id=0, proposal_id=1)

    def test_persona_finding_enforces_literals(self):
        finding = _SCHEMAS_MODULE.PersonaFinding(
            category="coverage_gap",
            severity="high",
            summary="Mancano allegati firmati",
            scope_type="proposal_section",
            scope_id="12",
            supporting_refs=["req-7"],
        )
        self.assertEqual(finding.scope_id, "12")
        self.assertEqual(finding.severity, "high")

    def test_persona_finding_rejects_bad_category(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            _SCHEMAS_MODULE.PersonaFinding(
                category="vibes_check",
                severity="high",
                summary="...",
                scope_type="proposal_section",
                scope_id="12",
            )

    def test_run_response_defaults_to_contract_version(self):
        response = _SCHEMAS_MODULE.RehearsalRunResponse(
            id=1,
            tender_id=1,
            proposal_id=2,
            mode="full",
            status="pending",
        )
        self.assertEqual(
            response.version,
            _SCHEMAS_MODULE.REHEARSAL_CONTRACT_VERSION,
        )
        self.assertEqual(response.persona_results, [])
        self.assertEqual(response.recommendations, [])

    def test_recommendation_response_defaults(self):
        recommendation = _SCHEMAS_MODULE.RehearsalRecommendationResponse(
            scope_type="requirement",
            scope_id="req-7",
            rationale="Evidenza insufficiente",
            source_persona_id="compliance_officer",
        )
        self.assertEqual(recommendation.severity, "medium")
        self.assertFalse(recommendation.is_blocking)
        self.assertEqual(recommendation.status, "proposed")
        self.assertIsNone(recommendation.linked_rework_action_id)


class RehearsalModelExportsTests(unittest.TestCase):
    def test_rehearsal_models_exported_from_app_models(self):
        for attr in (
            "RehearsalRun",
            "RehearsalPersonaResult",
            "RehearsalRecommendation",
            "RehearsalRunStatus",
            "RehearsalMode",
            "RehearsalRecommendationStatus",
        ):
            self.assertTrue(hasattr(_MODELS, attr), f"missing export: {attr}")

    def test_rehearsal_run_tablename(self):
        self.assertEqual(_MODELS.RehearsalRun.__tablename__, "rehearsal_runs")
        self.assertEqual(
            _MODELS.RehearsalPersonaResult.__tablename__,
            "rehearsal_persona_results",
        )
        self.assertEqual(
            _MODELS.RehearsalRecommendation.__tablename__,
            "rehearsal_recommendations",
        )

    def test_rehearsal_run_status_enum_values(self):
        self.assertEqual(
            {member.value for member in _MODELS.RehearsalRunStatus},
            {"pending", "running", "completed", "failed", "cancelled"},
        )

    def test_rehearsal_mode_enum_values(self):
        self.assertEqual(
            {member.value for member in _MODELS.RehearsalMode},
            {"full", "section", "pre_gate"},
        )

    def test_rehearsal_recommendation_status_enum_values(self):
        self.assertEqual(
            {member.value for member in _MODELS.RehearsalRecommendationStatus},
            {"proposed", "accepted", "dismissed"},
        )

    def test_persona_result_defaults_are_empty_containers(self):
        columns = {col.name: col for col in _MODELS.RehearsalPersonaResult.__table__.columns}
        self.assertIn("findings_json", columns)
        self.assertIn("questions_json", columns)
        self.assertIn("metrics_json", columns)

        # SQLAlchemy wraps `default=list/dict` in a callable that takes
        # an execution context.  Invoke with ``None`` to get a fresh
        # empty container and assert its type.
        self.assertEqual(columns["findings_json"].default.arg(None), [])
        self.assertEqual(columns["questions_json"].default.arg(None), [])
        self.assertEqual(columns["metrics_json"].default.arg(None), {})

    def test_recommendation_links_to_rework_actions(self):
        columns = {col.name: col for col in _MODELS.RehearsalRecommendation.__table__.columns}
        fk_cols = columns["linked_rework_action_id"].foreign_keys
        self.assertEqual(len(fk_cols), 1)
        target = next(iter(fk_cols)).target_fullname
        self.assertEqual(target, "rework_actions.id")


if __name__ == "__main__":
    unittest.main()
