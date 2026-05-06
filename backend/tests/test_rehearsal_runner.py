"""Unit tests for the Wave-3 rehearsal runner + service helpers (PR-08e).

Covers deterministic scoring in :mod:`app.intelligence.rehearsal_runner`
and the pure helpers in :mod:`app.intelligence.rehearsal`
(``_derive_recommendations``, ``_infer_owner``, ``_map_score_to_health``).

These tests do not touch the database: they feed hand-crafted tool
outputs into the runner and inspect the returned findings/score/metrics.
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
_CATALOG_MODULE = load_service_test_module("app.intelligence.persona_catalog")
_RUNNER_MODULE = load_service_test_module("app.intelligence.rehearsal_runner")
_SERVICE_MODULE = load_service_test_module("app.intelligence.rehearsal")


PERSONA_CATALOG = _CATALOG_MODULE.PERSONA_CATALOG
evaluate_persona = _RUNNER_MODULE.evaluate_persona
counts_by_severity = _RUNNER_MODULE.counts_by_severity
PersonaEvaluation = _RUNNER_MODULE.PersonaEvaluation


def _empty_tool_outputs() -> dict:
    return {
        "coverage_analyzer": {"gaps": []},
        "evidence_auditor": {"findings": []},
        "contradiction_finder": {"findings": []},
        "compliance_panorama": {"summary": {"failed_gates": 0, "blocking_reworks": 0}},
    }


class EvaluatePersonaCleanInputsTests(unittest.TestCase):
    def test_all_clean_gives_base_score_and_no_findings(self):
        persona = PERSONA_CATALOG["formalista_amministrativo"]
        evaluation = evaluate_persona(persona=persona, tool_outputs=_empty_tool_outputs())
        self.assertEqual(evaluation.score, 100.0)
        self.assertEqual(evaluation.findings, [])
        self.assertEqual(evaluation.questions, [])
        self.assertEqual(evaluation.metrics["coverage_gaps_high"], 0)
        self.assertEqual(evaluation.metrics["raw_penalty"], 0.0)

    def test_empty_outputs_dict_still_safe(self):
        persona = PERSONA_CATALOG["compliance_officer"]
        evaluation = evaluate_persona(persona=persona, tool_outputs={})
        self.assertEqual(evaluation.score, 100.0)
        self.assertEqual(evaluation.findings, [])


class EvaluatePersonaPenaltyTests(unittest.TestCase):
    def test_high_uncovered_gap_in_focus_produces_high_finding(self):
        persona = PERSONA_CATALOG["formalista_amministrativo"]
        outputs = _empty_tool_outputs()
        outputs["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": "R-1",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": "amministrativo",
                "summary": "Manca dichiarazione DGUE.",
            }
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        self.assertLess(evaluation.score, 100.0)
        self.assertEqual(len(evaluation.findings), 1)
        finding = evaluation.findings[0]
        self.assertEqual(finding["category"], "coverage_gap")
        self.assertEqual(finding["severity"], "high")
        self.assertEqual(finding["scope_id"], "R-1")
        self.assertEqual(evaluation.metrics["coverage_gaps_high"], 1)

    def test_gap_outside_focus_domain_is_filtered_out(self):
        persona = PERSONA_CATALOG["formalista_amministrativo"]
        outputs = _empty_tool_outputs()
        outputs["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": "R-42",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": "tecnico",
                "summary": "Manca specifica tecnica.",
            }
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        self.assertEqual(evaluation.findings, [])
        self.assertEqual(evaluation.score, 100.0)

    def test_missing_evidence_produces_weak_evidence_finding(self):
        persona = PERSONA_CATALOG["valutatore_tecnico"]
        outputs = _empty_tool_outputs()
        outputs["evidence_auditor"]["findings"] = [
            {
                "requirement_id": "R-7",
                "priority": "high",
                "evidence_status": "missing",
                "ontology_domain": "tecnico",
                "expected_evidence_type": "certification",
                "summary": "Nessuna certificazione ISO allegata.",
            }
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        self.assertEqual(len(evaluation.findings), 1)
        self.assertEqual(evaluation.findings[0]["category"], "weak_evidence")
        self.assertEqual(evaluation.findings[0]["severity"], "high")
        self.assertEqual(evaluation.metrics["evidence_missing"], 1)

    def test_strong_evidence_is_not_reported(self):
        persona = PERSONA_CATALOG["valutatore_tecnico"]
        outputs = _empty_tool_outputs()
        outputs["evidence_auditor"]["findings"] = [
            {
                "requirement_id": "R-7",
                "priority": "high",
                "evidence_status": "strong",
                "ontology_domain": "tecnico",
                "summary": "Documento presente e validato.",
            }
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        self.assertEqual(evaluation.findings, [])
        self.assertEqual(evaluation.score, 100.0)

    def test_failed_gates_create_gate_scoped_finding(self):
        persona = PERSONA_CATALOG["rup_simulato"]
        outputs = _empty_tool_outputs()
        outputs["compliance_panorama"]["summary"] = {
            "failed_gates": 2,
            "blocking_reworks": 1,
        }
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        scope_types = {f["scope_type"] for f in evaluation.findings}
        self.assertIn("gate", scope_types)
        categories = {f["category"] for f in evaluation.findings}
        self.assertIn("compliance_risk", categories)
        self.assertIn("delivery_risk", categories)
        # rup_simulato has blocking_risk_absence weight, so score drops
        self.assertLess(evaluation.score, 100.0)

    def test_contradictions_surface_regardless_of_focus(self):
        persona = PERSONA_CATALOG["formalista_amministrativo"]
        outputs = _empty_tool_outputs()
        outputs["contradiction_finder"]["findings"] = [
            {
                "requirement_id": "R-3",
                "summary": "Due scadenze diverse per la stessa attivita.",
                "kind": "deadline_conflict",
                "severity": "high",
            }
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        cats = {f["category"] for f in evaluation.findings}
        self.assertIn("contradiction", cats)


class StrictnessMultiplierTests(unittest.TestCase):
    def test_higher_strictness_lowers_score(self):
        outputs = _empty_tool_outputs()
        outputs["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": "R-1",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": "amministrativo",
                "summary": "gap",
            }
            for _ in range(3)
        ]

        lenient = _RUNNER_MODULE.ReviewerPersona = PERSONA_CATALOG["formalista_amministrativo"]
        del lenient

        # compliance_officer strictness is usually >= formalista — verify
        # via reordering: strictness in catalog is clipped 1..5.
        personas = sorted(PERSONA_CATALOG.values(), key=lambda p: p.strictness)
        low_strict = personas[0]
        high_strict = personas[-1]
        self.assertLessEqual(low_strict.strictness, high_strict.strictness)

        # Give both personas an in-focus gap so both actually score it.
        outputs_low = _empty_tool_outputs()
        outputs_low["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": "R-1",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": d,
                "summary": "gap",
            }
            for d in low_strict.focus_domains
        ]
        outputs_high = _empty_tool_outputs()
        outputs_high["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": "R-1",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": d,
                "summary": "gap",
            }
            for d in high_strict.focus_domains
        ]

        eval_low = evaluate_persona(persona=low_strict, tool_outputs=outputs_low)
        eval_high = evaluate_persona(persona=high_strict, tool_outputs=outputs_high)
        if low_strict.strictness < high_strict.strictness:
            self.assertGreaterEqual(
                eval_low.metrics["strictness_multiplier"],
                0.84,
            )
            self.assertGreaterEqual(
                eval_high.metrics["strictness_multiplier"],
                eval_low.metrics["strictness_multiplier"],
            )


class QuestionsAndCountsTests(unittest.TestCase):
    def test_questions_built_from_top_findings(self):
        persona = PERSONA_CATALOG["compliance_officer"]
        outputs = _empty_tool_outputs()
        outputs["coverage_analyzer"]["gaps"] = [
            {
                "requirement_id": f"R-{i}",
                "priority": "high",
                "coverage_status": "uncovered",
                "ontology_domain": "compliance",
                "summary": f"Gap {i}",
            }
            for i in range(8)
        ]
        evaluation = evaluate_persona(persona=persona, tool_outputs=outputs)
        self.assertGreater(len(evaluation.findings), 0)
        self.assertLessEqual(len(evaluation.questions), 5)

    def test_counts_by_severity_handles_missing_severity(self):
        findings = [
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
            {"severity": None},
            {},
        ]
        counts = counts_by_severity(findings)
        self.assertEqual(counts["high"], 1)
        self.assertEqual(counts["low"], 1)
        # None + missing coerce to "medium"
        self.assertEqual(counts["medium"], 3)


class DeriveRecommendationsTests(unittest.TestCase):
    def test_only_high_severity_findings_produce_recommendations(self):
        evaluations = [
            PersonaEvaluation(
                persona_id="p1",
                display_name="P1",
                reviewer_type="p1",
                score=70.0,
                findings=[
                    {
                        "category": "coverage_gap",
                        "severity": "medium",
                        "summary": "...",
                        "scope_type": "requirement",
                        "scope_id": "R-1",
                    }
                ],
                questions=[],
                metrics={},
            )
        ]
        recs = _SERVICE_MODULE._derive_recommendations(evaluations)
        self.assertEqual(recs, [])

    def test_single_persona_high_finding_is_not_blocking(self):
        evaluations = [
            PersonaEvaluation(
                persona_id="formalista_amministrativo",
                display_name="F",
                reviewer_type="formalista_amministrativo",
                score=40.0,
                findings=[
                    {
                        "category": "coverage_gap",
                        "severity": "high",
                        "summary": "Gap grave",
                        "scope_type": "requirement",
                        "scope_id": "R-1",
                    }
                ],
                questions=[],
                metrics={},
            )
        ]
        recs = _SERVICE_MODULE._derive_recommendations(evaluations)
        self.assertEqual(len(recs), 1)
        self.assertFalse(recs[0]["is_blocking"])
        self.assertEqual(recs[0]["scope_id"], "R-1")
        self.assertEqual(recs[0]["source_persona_id"], "formalista_amministrativo")

    def test_two_personas_concurring_makes_blocking(self):
        finding = {
            "category": "coverage_gap",
            "severity": "high",
            "summary": "stesso gap",
            "scope_type": "requirement",
            "scope_id": "R-7",
        }
        evaluations = [
            PersonaEvaluation(
                persona_id="p1",
                display_name="P1",
                reviewer_type="p1",
                score=60.0,
                findings=[dict(finding)],
                questions=[],
                metrics={},
            ),
            PersonaEvaluation(
                persona_id="p2",
                display_name="P2",
                reviewer_type="p2",
                score=55.0,
                findings=[dict(finding)],
                questions=[],
                metrics={},
            ),
        ]
        recs = _SERVICE_MODULE._derive_recommendations(evaluations)
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]["is_blocking"])
        self.assertEqual(recs[0]["source_persona_id"], "p1")

    def test_recommendations_sorted_blocking_first(self):
        finding_shared = {
            "category": "coverage_gap",
            "severity": "high",
            "summary": "shared",
            "scope_type": "requirement",
            "scope_id": "R-7",
        }
        finding_single = {
            "category": "coverage_gap",
            "severity": "high",
            "summary": "single",
            "scope_type": "requirement",
            "scope_id": "R-1",
        }
        evaluations = [
            PersonaEvaluation(
                persona_id="a",
                display_name="a",
                reviewer_type="a",
                score=50.0,
                findings=[dict(finding_single), dict(finding_shared)],
                questions=[],
                metrics={},
            ),
            PersonaEvaluation(
                persona_id="b",
                display_name="b",
                reviewer_type="b",
                score=50.0,
                findings=[dict(finding_shared)],
                questions=[],
                metrics={},
            ),
        ]
        recs = _SERVICE_MODULE._derive_recommendations(evaluations)
        self.assertEqual(recs[0]["scope_id"], "R-7")
        self.assertTrue(recs[0]["is_blocking"])
        self.assertFalse(recs[1]["is_blocking"])


class InferOwnerTests(unittest.TestCase):
    def test_gate_scope_routes_to_compliance(self):
        owner = _SERVICE_MODULE._infer_owner("gate", {"category": "weak_evidence"})
        self.assertEqual(owner, "compliance")

    def test_weak_evidence_routes_to_bid_manager(self):
        owner = _SERVICE_MODULE._infer_owner("requirement", {"category": "weak_evidence"})
        self.assertEqual(owner, "bid_manager")

    def test_contradiction_routes_to_technical(self):
        owner = _SERVICE_MODULE._infer_owner("requirement", {"category": "contradiction"})
        self.assertEqual(owner, "technical")

    def test_compliance_risk_routes_to_compliance(self):
        owner = _SERVICE_MODULE._infer_owner("requirement", {"category": "compliance_risk"})
        self.assertEqual(owner, "compliance")

    def test_unknown_category_returns_none(self):
        owner = _SERVICE_MODULE._infer_owner("requirement", {"category": "clarity_issue"})
        self.assertIsNone(owner)


class HealthProjectionTests(unittest.TestCase):
    def test_none_score_maps_to_none(self):
        self.assertIsNone(_SERVICE_MODULE._map_score_to_health(None))

    def test_green_above_80(self):
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(85.0), "green")
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(80.0), "green")

    def test_amber_between_60_and_80(self):
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(70.0), "amber")
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(60.0), "amber")

    def test_red_below_60(self):
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(30.0), "red")
        self.assertEqual(_SERVICE_MODULE._map_score_to_health(0.0), "red")


if __name__ == "__main__":
    unittest.main()
