"""Tests for tender requirement materialization from extracted candidates."""

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
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

_MODELS = load_models_test_module()
_SERVICE_MODULE = load_service_test_module("app.services.tender_requirements")


class TenderRequirementMaterializationTests(unittest.TestCase):
    def test_apply_extracted_requirement_candidates_keeps_reference_as_category_when_no_semantic_category_exists(self) -> None:
        tender = _MODELS.Tender(id=201, title="Services Tender")
        tender.requirements = []

        created = _SERVICE_MODULE.apply_extracted_requirement_candidates(
            tender,
            [
                {
                    "summary": "Provide signed annex A.",
                    "reference": "Section 1",
                    "priority": "high",
                }
            ],
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].category, "Section 1")

    def test_apply_extracted_requirement_candidates_preserves_llm_semantic_category(self) -> None:
        tender = _MODELS.Tender(id=202, title="Participation Tender")
        tender.requirements = []

        created = _SERVICE_MODULE.apply_extracted_requirement_candidates(
            tender,
            [
                {
                    "summary": "The bidder must provide ISO 27001 certification.",
                    "reference": "Mandatory Requirements",
                    "category": "certifications",
                    "priority": "high",
                }
            ],
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].category, "certifications")


if __name__ == "__main__":
    unittest.main()
