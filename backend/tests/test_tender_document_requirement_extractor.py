"""Tests for the provider-agnostic tender document requirement orchestrator."""

from __future__ import annotations

import json
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

_SERVICE_MODULE = load_service_test_module("app.services.tender_document_requirement_extractor")


class _FakeGenerator:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, dict, float | None, int | None]] = []

    async def generate(self, template, variables, temperature=None, max_tokens=None):
        self.calls.append((template, variables, temperature, max_tokens))
        return SimpleNamespace(text=json.dumps(self.response))


class _FailingGenerator:
    async def generate(self, template, variables, temperature=None, max_tokens=None):
        del template, variables, temperature, max_tokens
        raise RuntimeError(
            "OpenAI-compatible completion generation failed with status 502: upstream unavailable"
        )


class TenderDocumentRequirementExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_tender_participation_requirements_uses_participation_prompt(
        self,
    ) -> None:
        generator = _FakeGenerator(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [
                    {
                        "requirement_text": "L'operatore economico deve possedere la certificazione ISO 27001.",
                        "category": "certifications",
                        "priority": "high",
                        "confidence": 0.9,
                        "citations": [
                            {
                                "source_reference": "Requisiti di partecipazione",
                                "quote": "L'operatore economico deve possedere la certificazione ISO 27001.",
                            }
                        ],
                    }
                ],
            }
        )
        fake_settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=True,
            requirement_extraction_llm_v2_rollout_percent=100,
            requirement_extraction_llm_v2_tender_ids="",
            requirement_extraction_llm_v2_blocked_tender_ids="",
            requirement_extraction_llm_v2_max_sections=12,
            requirement_extraction_llm_v2_max_tokens=1200,
        )

        result = await _SERVICE_MODULE.extract_tender_participation_requirements(
            generator=generator,
            document_text="",
            section_texts={
                "Requisiti di partecipazione": "L'operatore economico deve possedere la certificazione ISO 27001."
            },
            source_document_ref="tenders/91/bando.pdf",
            tender_id=91,
            fallback_candidates=[
                {
                    "summary": "Fallback requirement",
                    "reference": "Section 1",
                    "priority": "medium",
                }
            ],
            settings=fake_settings,
        )

        self.assertEqual(result.extraction_method, "llm_v2")
        self.assertEqual(result.requirement_scope, "participation")
        self.assertEqual(result.extractor_pipeline, "tender_document_llm_participation_v1")
        self.assertEqual(generator.calls[0][0], "participation_requirement_extractor_v1")
        self.assertEqual(result.candidates[0]["category"], "certifications")
        self.assertEqual(result.candidates[0]["requirement_scope"], "participation")
        self.assertEqual(
            result.candidates[0]["extractor_pipeline"], "tender_document_llm_participation_v1"
        )

    async def test_extract_tender_participation_requirements_keeps_heuristic_fallback_warning(
        self,
    ) -> None:
        fake_settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=True,
            requirement_extraction_llm_v2_rollout_percent=100,
            requirement_extraction_llm_v2_tender_ids="",
            requirement_extraction_llm_v2_blocked_tender_ids="",
            requirement_extraction_llm_v2_max_sections=12,
            requirement_extraction_llm_v2_max_tokens=1200,
        )

        result = await _SERVICE_MODULE.extract_tender_participation_requirements(
            generator=_FailingGenerator(),
            document_text="The bidder must provide annex A and the signed declaration for admission to the procedure.",
            section_texts={
                "Document": "The bidder must provide annex A and the signed declaration for admission to the procedure."
            },
            source_document_ref="tenders/92/bando.pdf",
            tender_id=92,
            fallback_candidates=[
                {
                    "summary": "The bidder must provide annex A.",
                    "reference": "Document",
                    "priority": "high",
                }
            ],
            settings=fake_settings,
        )

        self.assertEqual(result.extraction_method, "heuristic_v1")
        self.assertEqual(result.requirement_scope, "general")
        self.assertEqual(result.extractor_pipeline, "heuristic_fallback_v1")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0]["status_code"], 502)
        self.assertEqual(result.candidates[0]["requirement_scope"], "general")


if __name__ == "__main__":
    unittest.main()
