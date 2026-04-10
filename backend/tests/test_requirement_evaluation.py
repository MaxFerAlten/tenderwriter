"""Unit tests for requirement pipeline evaluation helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from test_module_loaders import load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

_SERVICE_MODULE = load_service_test_module("app.services.requirement_evaluation")
_CLI_MODULE = load_service_test_module("app.evaluate_requirements")


class RequirementEvaluationTests(unittest.TestCase):
    def test_evaluate_requirement_pipeline_cases_reports_perfect_baseline(self) -> None:
        report = _SERVICE_MODULE.evaluate_requirement_pipeline_cases(
            [
                {
                    "id": "case-1",
                    "expected_requirements": [
                        {"key": "iso", "text": "The bidder must provide ISO 27001 certification."},
                    ],
                    "predicted_requirements": [
                        {
                            "canonical_text": "The bidder must provide ISO 27001 certification.",
                            "citations": [{"quote": "provide ISO 27001 certification"}],
                            "review_state": "approved",
                        },
                    ],
                    "expected_relations": [
                        {
                            "source_text": "The clarification requires ISO 27001 certification.",
                            "target_text": "The bidder must provide ISO 27001 certification.",
                            "relation_type": "overrides",
                        }
                    ],
                    "predicted_relations": [
                        {
                            "source_requirement_text": "The clarification requires ISO 27001 certification.",
                            "target_requirement_text": "The bidder must provide ISO 27001 certification.",
                            "relation_type": "overrides",
                        }
                    ],
                }
            ]
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.case_count, 1)
        self.assertEqual(report.requirement_recall, 1.0)
        self.assertEqual(report.requirement_precision, 1.0)
        self.assertEqual(report.citation_coverage, 1.0)
        self.assertEqual(report.relation_recall, 1.0)
        self.assertEqual(report.review_rate, 0.0)

    def test_evaluate_requirement_pipeline_cases_flags_missing_coverage_and_conflicts(self) -> None:
        report = _SERVICE_MODULE.evaluate_requirement_pipeline_cases(
            [
                {
                    "id": "case-2",
                    "expected_requirements": [
                        {"text": "Provide warranty coverage for 12 months."},
                        {"text": "Provide warranty coverage for 24 months."},
                    ],
                    "predicted_requirements": [
                        {
                            "canonical_text": "Provide warranty coverage for 12 months.",
                            "citations": [],
                            "review_state": "pending",
                        },
                    ],
                    "expected_relations": [
                        {
                            "source_text": "Provide warranty coverage for 12 months.",
                            "target_text": "Provide warranty coverage for 24 months.",
                            "relation_type": "conflicts_with",
                        }
                    ],
                    "predicted_relations": [],
                }
            ],
            thresholds=_SERVICE_MODULE.RequirementEvaluationThresholds(
                min_requirement_recall=0.9,
                min_requirement_precision=0.8,
                min_citation_coverage=0.9,
                min_conflict_detection_recall=0.9,
            ),
        )

        self.assertFalse(report.passed)
        self.assertAlmostEqual(report.requirement_recall, 0.5)
        self.assertEqual(report.requirement_precision, 1.0)
        self.assertEqual(report.citation_coverage, 0.0)
        self.assertEqual(report.conflict_detection_recall, 0.0)
        self.assertEqual(report.review_rate, 1.0)
        self.assertIn("requirement_recall", report.failures)
        self.assertIn("citation_coverage", report.failures)
        self.assertIn("conflict_detection_recall", report.failures)

    def test_load_requirement_evaluation_payload_from_json_file(self) -> None:
        payload = {
            "schema_version": "requirement_evaluation.gold.v1",
            "cases": [
                {
                    "id": "case-file",
                    "expected_requirements": [{"text": "Submit the technical plan."}],
                    "predicted_requirements": [
                        {
                            "text": "Submit the technical plan.",
                            "citations": [{"quote": "Submit the technical plan."}],
                        }
                    ],
                }
            ]
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name

        try:
            loaded = _SERVICE_MODULE.load_requirement_evaluation_payload(path)
        finally:
            os.remove(path)

        report = _SERVICE_MODULE.evaluate_requirement_pipeline_payload(loaded)
        self.assertTrue(report.passed)
        self.assertEqual(report.case_count, 1)

    def test_load_requirement_evaluation_payload_rejects_malformed_gold_set(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump({"schema_version": "requirement_evaluation.gold.v1", "cases": []}, handle)
            path = handle.name

        try:
            with self.assertRaisesRegex(ValueError, "non-empty cases array"):
                _SERVICE_MODULE.load_requirement_evaluation_payload(path)
        finally:
            os.remove(path)

    def test_negative_case_without_expected_items_is_valid_and_penalizes_false_positives(self) -> None:
        payload = {
            "schema_version": "requirement_evaluation.gold.v1",
            "cases": [
                {
                    "id": "negative-thesis-case",
                    "negative_case": True,
                    "expected_requirements": [],
                    "predicted_requirements": [
                        {
                            "canonical_text": "This mathematical fragment must be ignored.",
                            "citations": [{"quote": "must be ignored"}],
                            "review_state": "pending",
                        }
                    ],
                }
            ],
        }

        report = _SERVICE_MODULE.evaluate_requirement_pipeline_payload(payload)

        self.assertFalse(report.passed)
        self.assertEqual(report.expected_requirements, 0)
        self.assertEqual(report.predicted_requirements, 1)
        self.assertEqual(report.requirement_precision, 0.0)
        self.assertEqual(report.requirement_recall, 1.0)
        self.assertIn("requirement_precision", report.failures)
        self.assertNotIn("requirement_recall", report.failures)

    def test_synthetic_smoke_fixture_passes_quality_gate(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "requirement_evaluation" / "gold_smoke.json"

        report = _SERVICE_MODULE.evaluate_requirement_pipeline_payload(
            _SERVICE_MODULE.load_requirement_evaluation_payload(fixture_path)
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.case_count, 1)
        self.assertEqual(report.requirement_recall, 1.0)
        self.assertEqual(report.citation_coverage, 1.0)

    def test_evaluation_cli_parses_threshold_options(self) -> None:
        args = _CLI_MODULE.build_parser().parse_args(
            [
                "gold.json",
                "--min-recall",
                "0.9",
                "--min-precision",
                "0.85",
                "--min-citation-coverage",
                "0.95",
                "--min-conflict-recall",
                "0.75",
                "--report-file",
                "report.json",
                "--json",
            ]
        )

        self.assertEqual(args.gold_file, "gold.json")
        self.assertEqual(args.min_recall, 0.9)
        self.assertEqual(args.min_precision, 0.85)
        self.assertEqual(args.min_citation_coverage, 0.95)
        self.assertEqual(args.min_conflict_recall, 0.75)
        self.assertEqual(args.report_file, "report.json")
        self.assertTrue(args.json)

    def test_evaluation_cli_writes_report_file(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "requirement_evaluation" / "gold_smoke.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "reports" / "requirement-evaluation.json"

            exit_code = _CLI_MODULE.main(
                [
                    str(fixture_path),
                    "--report-file",
                    str(report_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report_payload["passed"])
            self.assertEqual(report_payload["case_count"], 1)


if __name__ == "__main__":
    unittest.main()
