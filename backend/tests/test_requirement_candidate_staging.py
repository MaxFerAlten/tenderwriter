"""Unit tests for raw requirement candidate staging."""

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

_SERVICE_MODULE = load_service_test_module("app.services.requirement_candidates")

stage_extracted_requirement_candidates = _SERVICE_MODULE.stage_extracted_requirement_candidates


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self._next_id = 1

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                setattr(instance, "id", self._next_id)
                self._next_id += 1


class RequirementCandidateStagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_extracted_requirement_candidates_preserves_provenance(self) -> None:
        db = _FakeAsyncSession()

        extraction_run, staged_candidates = await stage_extracted_requirement_candidates(
            db,
            tender_id=11,
            actor_id=7,
            source_document_ref="tenders/11/rfp.pdf",
            filename="rfp.pdf",
            extraction_method="heuristic_v1",
            candidates=[
                {
                    "summary": "The bidder must provide ISO 27001 certification.",
                    "reference": "Mandatory Requirements",
                    "priority": "high",
                    "confidence": 0.91,
                }
            ],
            metadata={"content_type": "application/pdf"},
        )

        self.assertEqual(extraction_run.tender_id, 11)
        self.assertEqual(extraction_run.actor_id, 7)
        self.assertEqual(extraction_run.source_document_ref, "tenders/11/rfp.pdf")
        self.assertEqual(extraction_run.filename, "rfp.pdf")
        self.assertEqual(extraction_run.extraction_method, "heuristic_v1")
        self.assertEqual(extraction_run.candidate_count, 1)
        self.assertEqual(extraction_run.metadata_json["content_type"], "application/pdf")
        self.assertEqual(extraction_run.metadata_json["raw_candidate_count"], 1)
        self.assertEqual(extraction_run.metadata_json["staged_candidate_count"], 1)
        self.assertEqual(len(staged_candidates), 1)
        self.assertEqual(staged_candidates[0].extraction_run_id, extraction_run.id)
        self.assertEqual(staged_candidates[0].source_reference, "Mandatory Requirements")
        self.assertEqual(staged_candidates[0].priority, "high")
        self.assertAlmostEqual(staged_candidates[0].confidence, 0.91)

    async def test_stage_extracted_requirement_candidates_preserves_llm_v2_citations_in_raw_payload(self) -> None:
        db = _FakeAsyncSession()

        extraction_run, staged_candidates = await stage_extracted_requirement_candidates(
            db,
            tender_id=13,
            actor_id=7,
            source_document_ref="tenders/13/rfp.pdf",
            filename="rfp.pdf",
            extraction_method="llm_v2",
            candidates=[
                {
                    "summary": "The bidder must provide ISO 27001 certification.",
                    "reference": "Mandatory Requirements",
                    "category": "certifications",
                    "priority": "high",
                    "confidence": 0.91,
                    "schema_version": "requirement_extraction_v2.schema.v1",
                    "citations": [
                        {
                            "source_document_ref": "tenders/13/rfp.pdf",
                            "section_path": "Mandatory Requirements",
                            "quote": "The bidder must provide ISO 27001 certification.",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(extraction_run.extraction_method, "llm_v2")
        self.assertEqual(len(staged_candidates), 1)
        self.assertEqual(staged_candidates[0].category, "certifications")
        raw_candidate = staged_candidates[0].metadata_json["raw_candidate"]
        self.assertEqual(raw_candidate["schema_version"], "requirement_extraction_v2.schema.v1")
        self.assertEqual(raw_candidate["citations"][0]["quote"], "The bidder must provide ISO 27001 certification.")

    async def test_stage_extracted_requirement_candidates_filters_duplicates_and_short_rows(self) -> None:
        db = _FakeAsyncSession()

        extraction_run, staged_candidates = await stage_extracted_requirement_candidates(
            db,
            tender_id=12,
            actor_id=None,
            source_document_ref="tenders/12/spec.docx",
            filename="spec.docx",
            extraction_method="heuristic_v1",
            candidates=[
                {
                    "summary": "Provide signed annex A.",
                    "reference": "Section 1",
                    "priority": "HIGH",
                },
                {
                    "summary": "Provide signed annex A.",
                    "reference": "Section 1",
                    "priority": "high",
                },
                {
                    "summary": "short",
                    "reference": "Section 2",
                    "priority": "medium",
                },
                {
                    "summary": "Include an implementation plan with milestones.",
                    "reference": "Section 3",
                    "priority": "unexpected",
                },
            ],
        )

        self.assertEqual(extraction_run.candidate_count, 2)
        self.assertEqual(extraction_run.metadata_json["raw_candidate_count"], 4)
        self.assertEqual(extraction_run.metadata_json["staged_candidate_count"], 2)
        self.assertEqual(len(staged_candidates), 2)
        self.assertEqual(
            [candidate.summary_text for candidate in staged_candidates],
            [
                "Provide signed annex A.",
                "Include an implementation plan with milestones.",
            ],
        )
        self.assertEqual(
            [candidate.priority for candidate in staged_candidates],
            ["high", "medium"],
        )
        self.assertGreaterEqual(db.flush_count, 2)


if __name__ == "__main__":
    unittest.main()
