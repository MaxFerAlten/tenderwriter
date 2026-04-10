"""Unit tests for grounded requirement verification."""

from __future__ import annotations

import os
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

_SERVICE_MODULE = load_service_test_module("app.services.requirement_verification")


class RequirementVerificationTests(unittest.TestCase):
    def test_verify_requirement_candidate_accepts_supported_citation(self) -> None:
        candidate = _SERVICE_MODULE.verify_requirement_candidate(
            {
                "summary": "The bidder must provide ISO 27001 certification.",
                "confidence": 0.91,
                "citations": [
                    {
                        "quote": "The bidder must provide ISO 27001 certification.",
                    }
                ],
            },
            source_text="The bidder must provide ISO 27001 certification.",
        )

        self.assertEqual(candidate["verification_state"], "verified")
        self.assertEqual(candidate["confidence"], 0.91)
        self.assertGreaterEqual(candidate["grounded_score"], 0.55)
        self.assertEqual(candidate["verification"]["reason"], "supported_by_citation")

    def test_verify_requirement_candidate_downgrades_partial_support(self) -> None:
        candidate = _SERVICE_MODULE.verify_requirement_candidate(
            {
                "summary": (
                    "The bidder must provide ISO 27001 certification, cyber insurance, "
                    "incident response plan, and disaster recovery runbook."
                ),
                "confidence": 0.92,
                "citations": [
                    {
                        "quote": "The bidder must provide ISO 27001 certification.",
                    }
                ],
            },
            source_text="The bidder must provide ISO 27001 certification.",
        )

        self.assertEqual(candidate["verification_state"], "downgraded")
        self.assertEqual(candidate["confidence"], 0.45)
        self.assertEqual(candidate["verification"]["reason"], "partially_supported_by_citation")

    def test_verify_requirement_candidate_rejects_quote_missing_from_source(self) -> None:
        candidate = _SERVICE_MODULE.verify_requirement_candidate(
            {
                "summary": "The bidder must provide ISO 27001 certification.",
                "confidence": 0.91,
                "citations": [
                    {
                        "quote": "The bidder must provide ISO 27001 certification.",
                    }
                ],
            },
            source_text="The tender describes delivery milestones only.",
        )

        self.assertEqual(candidate["verification_state"], "rejected")
        self.assertEqual(candidate["confidence"], 0.0)
        self.assertEqual(candidate["verification"]["reason"], "citation_quote_not_in_source")

    def test_verify_requirement_candidate_rejects_missing_citations(self) -> None:
        candidate = _SERVICE_MODULE.verify_requirement_candidate(
            {
                "summary": "The bidder must provide ISO 27001 certification.",
                "confidence": 0.91,
            }
        )

        self.assertEqual(candidate["verification_state"], "rejected")
        self.assertEqual(candidate["verification"]["reason"], "missing_citations")


if __name__ == "__main__":
    unittest.main()
