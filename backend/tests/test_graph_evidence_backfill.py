"""Tests for graph evidence chunk backfill helpers."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

_SERVICE_MODULE = load_service_test_module("app.services.graph_evidence_backfill")


class GraphEvidenceBackfillTests(unittest.IsolatedAsyncioTestCase):
    def test_build_evidence_chunk_payload_adds_ontology_and_provenance(self) -> None:
        payload = _SERVICE_MODULE.build_evidence_chunk_payload(
            "Il fornitore deve possedere certificazione ISO 27001.",
            {
                "doc_type": "tender",
                "tender_id": 42,
                "document_id": 7,
                "chunk_index": 3,
                "page_number": 36,
                "source_document_ref": "tenders/42/capitolato.pdf",
                "section_title": "Requisiti certificazioni",
                "extra": {"procedure_key": "oscat"},
            },
        )

        assert payload is not None
        self.assertEqual(payload["ontology_domain"], "compliance")
        self.assertEqual(payload["ontology_subdomain"], "certificazioni")
        self.assertEqual(payload["page_number"], 36)
        self.assertEqual(payload["procedure_key"], "oscat")
        self.assertTrue(payload["id"].startswith("evidence-"))

    async def test_backfill_graph_evidence_chunks_upserts_filtered_payloads(self) -> None:
        graph = SimpleNamespace(upsert_evidence_chunk=AsyncMock())

        count = await _SERVICE_MODULE.backfill_graph_evidence_chunks(
            graph,
            texts=[
                "Il fornitore deve possedere certificazione ISO 27001.",
                "Documento interno non tender.",
            ],
            metadatas=[
                {"doc_type": "tender", "chunk_index": 1, "page_number": 36},
                {"doc_type": "proposal", "chunk_index": 2},
            ],
            doc_type="tender",
        )

        self.assertEqual(count, 1)
        graph.upsert_evidence_chunk.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
