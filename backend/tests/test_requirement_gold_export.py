"""Unit tests for requirement gold-set export helpers."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

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

_EXPORT_MODULE = load_service_test_module("app.services.requirement_gold_export")
_EVALUATION_MODULE = load_service_test_module("app.services.requirement_evaluation")
_CLI_MODULE = load_service_test_module("app.export_requirement_gold_set")


class RequirementGoldExportTests(unittest.TestCase):
    def test_build_requirement_gold_set_case_uses_approved_as_expected_and_active_as_predicted(
        self,
    ) -> None:
        approved_requirement = SimpleNamespace(
            id=11,
            canonical_text="The bidder must provide ISO 27001 certification.",
            category="security",
            priority="high",
            confidence=0.94,
            source_count=1,
            review_state="approved",
            graph_state="active",
            metadata_json={
                "sources": [
                    {
                        "summary_text": "The bidder must provide ISO 27001 certification.",
                        "source_reference": "Section 2.1",
                        "source_document_ref": "disciplinare.pdf",
                        "filename": "disciplinare.pdf",
                        "document_role": "disciplinare",
                    }
                ]
            },
        )
        approved_dependency_requirement = SimpleNamespace(
            id=10,
            canonical_text="The bidder must register on the procurement portal.",
            category="administrative",
            priority="high",
            confidence=0.9,
            source_count=1,
            review_state="approved",
            graph_state="active",
            metadata_json={"sources": []},
        )
        pending_requirement = SimpleNamespace(
            id=12,
            canonical_text="The bidder should provide a draft operations plan.",
            category="operations",
            priority="medium",
            confidence=0.72,
            source_count=1,
            review_state="pending",
            graph_state="active",
            metadata_json={"sources": []},
        )
        obsolete_requirement = SimpleNamespace(
            id=13,
            canonical_text="Obsolete clause.",
            review_state="approved",
            graph_state="obsolete",
            metadata_json={"sources": []},
        )
        approved_relation = SimpleNamespace(
            id=21,
            source_requirement_id=10,
            target_requirement_id=11,
            source_requirement=approved_dependency_requirement,
            target_requirement=approved_requirement,
            relation_type="depends_on",
            confidence=0.81,
            review_state="approved",
            graph_state="active",
            metadata_json={"inference_method": "test"},
        )
        pending_endpoint_relation = SimpleNamespace(
            id=22,
            source_requirement_id=12,
            target_requirement_id=11,
            source_requirement=pending_requirement,
            target_requirement=approved_requirement,
            relation_type="depends_on",
            confidence=0.7,
            review_state="approved",
            graph_state="active",
            metadata_json={"inference_method": "test"},
        )

        case = _EXPORT_MODULE.build_requirement_gold_set_case(
            SimpleNamespace(id=7, title="Security tender"),
            [
                approved_dependency_requirement,
                approved_requirement,
                pending_requirement,
                obsolete_requirement,
            ],
            [approved_relation, pending_endpoint_relation],
        )

        self.assertEqual(case["id"], "tender-7")
        self.assertIn(
            "The bidder must provide ISO 27001 certification.",
            [item["text"] for item in case["expected_requirements"]],
        )
        self.assertEqual(len(case["predicted_requirements"]), 3)
        self.assertEqual(
            case["predicted_requirements"][1]["citations"][0]["source_reference"], "Section 2.1"
        )
        self.assertEqual(case["expected_relations"][0]["relation_type"], "depends_on")
        self.assertEqual(len(case["predicted_relations"]), 2)
        self.assertEqual(
            case["predicted_relations"][1]["source_requirement_text"],
            pending_requirement.canonical_text,
        )

    def test_build_requirement_gold_set_payload_is_evaluator_compatible(self) -> None:
        approved_requirement = SimpleNamespace(
            id=31,
            canonical_text="Submit the implementation plan.",
            category="delivery",
            priority="high",
            confidence=0.9,
            source_count=1,
            review_state="approved",
            graph_state="active",
            metadata_json={
                "sources": [
                    {
                        "summary_text": "Submit the implementation plan.",
                        "source_reference": "Section 4",
                    }
                ]
            },
        )
        case = _EXPORT_MODULE.build_requirement_gold_set_case(
            SimpleNamespace(id=3, title="Delivery tender"),
            [approved_requirement],
            [],
        )

        payload = _EXPORT_MODULE.build_requirement_gold_set_payload([case])

        _EVALUATION_MODULE.validate_requirement_evaluation_payload(payload)
        report = _EVALUATION_MODULE.evaluate_requirement_pipeline_payload(payload)
        self.assertTrue(report.passed)
        self.assertTrue(payload["metadata"]["draft_review_required"])

    def test_build_requirement_gold_set_payload_supports_negative_case_false_positive_benchmark(
        self,
    ) -> None:
        pending_false_positive = SimpleNamespace(
            id=51,
            canonical_text="The theorem must hold for each alternating path.",
            category="technical",
            priority="high",
            confidence=0.62,
            source_count=1,
            review_state="pending",
            graph_state="active",
            metadata_json={
                "sources": [{"summary_text": "The theorem must hold for each alternating path."}]
            },
        )
        case = _EXPORT_MODULE.build_requirement_gold_set_case(
            SimpleNamespace(id=5, title="Negative thesis fixture"),
            [pending_false_positive],
            [],
        )

        payload = _EXPORT_MODULE.build_requirement_gold_set_payload([case])
        report = _EVALUATION_MODULE.evaluate_requirement_pipeline_payload(payload)

        self.assertTrue(case["negative_case"])
        self.assertEqual(case["expected_requirements"], [])
        self.assertEqual(len(case["predicted_requirements"]), 1)
        self.assertFalse(report.passed)
        self.assertEqual(report.requirement_precision, 0.0)

    def test_build_requirement_gold_set_case_can_restrict_predictions_to_approved_only(
        self,
    ) -> None:
        approved_requirement = SimpleNamespace(
            id=41,
            canonical_text="Submit the QA plan.",
            review_state="approved",
            graph_state="active",
            metadata_json={"sources": []},
        )
        pending_requirement = SimpleNamespace(
            id=42,
            canonical_text="Submit the deployment plan.",
            review_state="pending",
            graph_state="active",
            metadata_json={"sources": []},
        )

        case = _EXPORT_MODULE.build_requirement_gold_set_case(
            SimpleNamespace(id=4, title="QA tender"),
            [approved_requirement, pending_requirement],
            [],
            include_pending_predictions=False,
        )

        self.assertEqual(len(case["expected_requirements"]), 1)
        self.assertEqual(len(case["predicted_requirements"]), 1)
        self.assertEqual(case["predicted_requirements"][0]["canonical_text"], "Submit the QA plan.")

    def test_export_cli_parses_scoped_output_options(self) -> None:
        args = _CLI_MODULE.build_parser().parse_args(
            [
                "--tender-id",
                "12",
                "--tender-id",
                "14",
                "--output",
                "reports/gold-draft.json",
                "--approved-only-predictions",
                "--skip-negative-cases",
            ]
        )

        self.assertEqual(args.tender_ids, [12, 14])
        self.assertEqual(args.output, "reports/gold-draft.json")
        self.assertTrue(args.approved_only_predictions)
        self.assertTrue(args.skip_negative_cases)


if __name__ == "__main__":
    unittest.main()
