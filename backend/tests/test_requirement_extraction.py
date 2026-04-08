"""Unit tests for tender requirement extraction and persistence helpers."""

import os
import unittest

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

from app.ingestion.pipeline import IngestionPipeline
from app.models import Tender, TenderRequirement, TenderStatus
from app.services.tender_requirements import apply_extracted_requirement_candidates


class RequirementExtractionTests(unittest.TestCase):
    def test_extract_requirement_candidates_from_mandatory_section(self) -> None:
        pipeline = IngestionPipeline(rag_engine=None)
        elements = [
            {
                "type": "Title",
                "text": "Mandatory Requirements",
                "metadata": {"section": "Mandatory Requirements"},
            },
            {
                "type": "Text",
                "text": (
                    "1. The bidder must provide ISO 27001 certification.\n"
                    "2. Deve includere un piano di continuita' operativa.\n"
                    "3. Company overview."
                ),
                "metadata": {"page_number": 1},
            },
        ]

        _, section_texts = pipeline._structure_elements(elements)
        candidates = pipeline.extract_requirement_candidates(elements, section_texts)
        summaries = [candidate["summary"].casefold() for candidate in candidates]

        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(any("iso 27001" in summary for summary in summaries))
        self.assertTrue(any("continuita' operativa" in summary for summary in summaries))
        self.assertTrue(all(candidate["priority"] in {"high", "medium", "low"} for candidate in candidates))

    def test_extract_requirement_candidates_ignores_academic_prose_with_modal_verbs(self) -> None:
        pipeline = IngestionPipeline(rag_engine=None)
        elements = [
            {
                "type": "Title",
                "text": "Capitolo 3 - Grafi",
                "metadata": {"section": "Capitolo 3 - Grafi"},
            },
            {
                "type": "Text",
                "text": (
                    "cammino M-alternante P per poter collegare due vertici esposti deve essere.\n"
                    "tutti i vertici di grado 2 allora deve essere un ciclo pari che alterna tra archi.\n"
                    "l'operatore deve risolvere il problema di ottimizzazione (2.3)."
                ),
                "metadata": {"page_number": 12},
            },
        ]

        _, section_texts = pipeline._structure_elements(elements)
        candidates = pipeline.extract_requirement_candidates(elements, section_texts)

        self.assertEqual(candidates, [])

    def test_apply_extracted_requirement_candidates_deduplicates_existing_rows(self) -> None:
        tender = Tender(id=7, title="Framework Tender", status=TenderStatus.DRAFT)
        tender.requirements = [
            TenderRequirement(
                requirement_text="The bidder must provide ISO 27001 certification",
                category="Mandatory Requirements",
                priority="high",
            )
        ]

        created = apply_extracted_requirement_candidates(
            tender,
            [
                {
                    "summary": "The bidder must provide ISO 27001 certification",
                    "reference": "Mandatory Requirements",
                    "priority": "high",
                },
                {
                    "summary": "Deve includere un piano di continuita' operativa.",
                    "reference": "Mandatory Requirements",
                    "priority": "medium",
                },
            ],
        )

        self.assertEqual(len(created), 1)
        self.assertEqual(len(tender.requirements), 2)
        self.assertEqual(created[0].priority, "medium")
        self.assertEqual(created[0].category, "Mandatory Requirements")
        self.assertEqual(created[0].compliance_status.value, "not_addressed")


if __name__ == "__main__":
    unittest.main()
