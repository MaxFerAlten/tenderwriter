# ruff: noqa: E501
"""Tests for tender requirement materialization from extracted candidates."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
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
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

_MODELS = load_models_test_module()
_SERVICE_MODULE = load_service_test_module("app.services.tender_requirements")


class TenderRequirementMaterializationTests(unittest.TestCase):
    def test_apply_extracted_requirement_candidates_keeps_reference_as_category_when_no_semantic_category_exists(
        self,
    ) -> None:
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

    def test_requirement_identity_hash_is_stable_for_text_normalization(self) -> None:
        first = _SERVICE_MODULE.compute_requirement_identity_hash(
            "  Deve garantire continuità operativa. ",
            tender_id=77,
        )
        second = _SERVICE_MODULE.compute_requirement_identity_hash(
            "deve garantire continuita operativa",
            tender_id=77,
        )
        other_tender = _SERVICE_MODULE.compute_requirement_identity_hash(
            "deve garantire continuita operativa",
            tender_id=78,
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, other_tender)
        self.assertEqual(len(first), 16)


class TenderRequirementGraphSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_tender_requirements_adds_identity_hash_to_graph_payload(self) -> None:
        tender = _MODELS.Tender(id=303, title="Cloud Tender")
        requirement = _MODELS.TenderRequirement(
            id=44,
            requirement_text="Il fornitore deve garantire continuita operativa.",
            category="technical",
            priority="high",
        )
        tender.requirements = [requirement]
        graph = SimpleNamespace(add_requirement=AsyncMock(), upsert_tender=AsyncMock())
        rag_engine = SimpleNamespace(ensure_initialized=AsyncMock(), graph_retriever=graph)

        with patch.object(
            _SERVICE_MODULE,
            "project_requirement_event",
            AsyncMock(),
        ):
            synced = await _SERVICE_MODULE.sync_tender_requirements_to_graph(rag_engine, tender)

        self.assertEqual(synced, 1)
        payload = graph.add_requirement.await_args.args[0]
        self.assertEqual(
            payload["identity_hash"],
            _SERVICE_MODULE.compute_requirement_identity_hash(
                requirement.requirement_text,
                tender_id=tender.id,
            ),
        )
        self.assertEqual(payload["ontology_domain"], "tecnico")
        self.assertEqual(payload["ontology_subdomain"], "sla_continuita")
        self.assertEqual(payload["ontology_version"], "tw-ontology-v1")
        self.assertEqual(payload["id"], "tender-303-requirement-44")


if __name__ == "__main__":
    unittest.main()
