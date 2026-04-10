"""Unit tests for LLM v2 requirement extraction."""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

from app.config import settings
from app.ingestion.pipeline import IngestionPipeline

_SERVICE_MODULE = load_service_test_module("app.services.requirement_extraction_v2")


class _FakeRagEngine:
    def __init__(self, generator=None) -> None:
        self.generator = generator

    def chunk_and_embed(self, *args, **kwargs):
        del args, kwargs
        return []

    def index_chunks(self, *args, **kwargs):
        del args, kwargs
        return []


class _FakeGenerator:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, dict, float | None, int | None]] = []

    async def generate(self, template, variables, temperature=None, max_tokens=None):
        self.calls.append((template, variables, temperature, max_tokens))
        return SimpleNamespace(text=json.dumps(self.response))


class _FailingGenerator:
    def __init__(self, error_message: str) -> None:
        self.error_message = error_message
        self.calls: list[tuple[str, dict, float | None, int | None]] = []

    async def generate(self, template, variables, temperature=None, max_tokens=None):
        self.calls.append((template, variables, temperature, max_tokens))
        raise RuntimeError(self.error_message)


class RequirementExtractionV2Tests(unittest.IsolatedAsyncioTestCase):
    def test_parse_requirement_extraction_v2_response_requires_citations(self) -> None:
        response = json.dumps(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [
                    {
                        "requirement_text": "The bidder must provide ISO 27001 certification.",
                        "category": "technical",
                        "priority": "must-have",
                        "confidence": 0.94,
                        "citations": [
                            {
                                "section_path": "Mandatory requirements",
                                "source_reference": "Section 2.1",
                                "quote": "The bidder must provide ISO 27001 certification.",
                            }
                        ],
                    },
                    {
                        "requirement_text": "This unsupported requirement must be ignored.",
                        "category": "technical",
                        "priority": "high",
                        "confidence": 0.5,
                        "citations": [],
                    },
                ],
            }
        )

        candidates = _SERVICE_MODULE.parse_requirement_extraction_v2_response(
            response,
            source_document_ref="tenders/12/rfp.pdf",
            section_path="Mandatory requirements",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["summary"], "The bidder must provide ISO 27001 certification.")
        self.assertEqual(candidates[0]["priority"], "high")
        self.assertEqual(candidates[0]["category"], "technical")
        self.assertEqual(candidates[0]["schema_version"], "requirement_extraction_v2.schema.v1")
        self.assertEqual(candidates[0]["extraction_method"], "llm_v2")
        self.assertEqual(candidates[0]["citations"][0]["source_document_ref"], "tenders/12/rfp.pdf")

    async def test_extract_requirement_candidates_v2_from_sections_calls_generator_with_schema_prompt(self) -> None:
        generator = _FakeGenerator(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [
                    {
                        "requirement_text": "Deve includere un piano di continuita operativa.",
                        "category": "technical",
                        "priority": "medium",
                        "confidence": 0.82,
                        "conditions": ["Applicabile al servizio principale"],
                        "citations": [
                            {
                                "source_reference": "Sezione 4",
                                "quote": "Deve includere un piano di continuita operativa.",
                            }
                        ],
                    }
                ],
            }
        )

        candidates = await _SERVICE_MODULE.extract_requirement_candidates_v2_from_sections(
            generator,
            document_text="",
            section_texts={"Sezione 4": "Deve includere un piano di continuita operativa."},
            source_document_ref="tenders/15/capitolato.pdf",
            max_sections=1,
            max_tokens=1200,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(generator.calls[0][0], "requirement_extractor_v2")
        self.assertEqual(generator.calls[0][1]["schema_version"], "requirement_extraction_v2.schema.v1")
        self.assertEqual(generator.calls[0][1]["section_path"], "Sezione 4")
        self.assertEqual(generator.calls[0][3], 1200)
        self.assertEqual(candidates[0]["conditions"], ["Applicabile al servizio principale"])
        self.assertEqual(candidates[0]["citations"][0]["section_path"], "Sezione 4")

    async def test_extract_requirement_candidates_v2_splits_oversized_sections_into_bounded_prompt_windows(self) -> None:
        generator = _FakeGenerator(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [],
            }
        )
        long_section = ("The bidder must provide a detailed delivery plan. " * 260).strip()

        candidates = await _SERVICE_MODULE.extract_requirement_candidates_v2_from_sections(
            generator,
            document_text="",
            section_texts={"Section 8": long_section},
            source_document_ref="tenders/21/capitolato.pdf",
            max_sections=3,
            max_tokens=2048,
            context_window=4096,
        )

        self.assertEqual(candidates, [])
        self.assertEqual(len(generator.calls), 3)
        max_input_chars = _SERVICE_MODULE._estimate_max_input_chars(
            context_window=4096,
            max_tokens=2048,
        )
        self.assertEqual(max_input_chars, 4608)
        for _, variables, _, _ in generator.calls:
            self.assertLessEqual(len(variables["document_text"]), max_input_chars)
            self.assertEqual(variables["section_path"], "Section 8")

    async def test_ingest_file_keeps_heuristic_extraction_when_llm_v2_flag_is_disabled(self) -> None:
        generator = _FakeGenerator({"requirements": []})
        pipeline = IngestionPipeline(_FakeRagEngine(generator=generator))
        elements = [
            {"type": "Title", "text": "Mandatory Requirements", "metadata": {"section": "Mandatory Requirements"}},
            {
                "type": "Text",
                "text": "The bidder must provide ISO 27001 certification.",
                "metadata": {"page_number": 1},
            },
        ]

        with patch.object(settings, "requirement_extraction_llm_v2_enabled", False), patch.object(
            pipeline,
            "_parse_document",
            return_value=elements,
        ):
            stats = await pipeline.ingest_file(
                file_path="rfp.pdf",
                document_id=15,
                doc_type="tender",
            )

        self.assertEqual(stats["requirement_extraction_method"], "heuristic_v1")
        self.assertEqual(generator.calls, [])
        self.assertGreaterEqual(stats["requirements_detected"], 1)

    async def test_ingest_file_can_use_llm_v2_candidates_when_flag_is_enabled(self) -> None:
        generator = _FakeGenerator(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [
                    {
                        "requirement_text": "The bidder must provide ISO 27001 certification.",
                        "category": "technical",
                        "priority": "high",
                        "confidence": 0.91,
                        "citations": [
                            {
                                "source_reference": "Mandatory Requirements",
                                "quote": "The bidder must provide ISO 27001 certification.",
                            }
                        ],
                    }
                ],
            }
        )
        pipeline = IngestionPipeline(_FakeRagEngine(generator=generator))
        elements = [
            {"type": "Title", "text": "Mandatory Requirements", "metadata": {"section": "Mandatory Requirements"}},
            {
                "type": "Text",
                "text": "The bidder must provide ISO 27001 certification.",
                "metadata": {"page_number": 1},
            },
        ]

        with patch.object(settings, "requirement_extraction_llm_v2_enabled", True), patch.object(
            pipeline,
            "_parse_document",
            return_value=elements,
        ):
            stats = await pipeline.ingest_file(
                file_path="rfp.pdf",
                document_id=16,
                doc_type="tender",
            )

        self.assertEqual(stats["requirement_extraction_method"], "llm_v2")
        self.assertEqual(stats["requirements_detected"], 1)
        self.assertEqual(stats["requirement_candidates"][0]["extraction_method"], "llm_v2")
        self.assertEqual(stats["requirement_candidates"][0]["citations"][0]["source_document_ref"], "rfp.pdf")
        self.assertEqual(stats["requirement_scope"], "participation")
        self.assertEqual(stats["requirement_extractor_pipeline"], "tender_document_llm_participation_v1")
        self.assertEqual(stats["requirement_candidates"][0]["requirement_scope"], "participation")
        self.assertEqual(stats["requirement_candidates"][0]["extractor_pipeline"], "tender_document_llm_participation_v1")
        self.assertEqual(generator.calls[0][0], "participation_requirement_extractor_v1")
        self.assertEqual(stats["warnings"], [])

    async def test_ingest_file_collects_llm_v2_warning_and_keeps_heuristic_fallback(self) -> None:
        generator = _FailingGenerator(
            "OpenAI-compatible completion generation failed with status 403: upstream denied access"
        )
        pipeline = IngestionPipeline(_FakeRagEngine(generator=generator))
        elements = [
            {"type": "Title", "text": "Mandatory Requirements", "metadata": {"section": "Mandatory Requirements"}},
            {
                "type": "Text",
                "text": "The bidder must provide ISO 27001 certification.",
                "metadata": {"page_number": 1},
            },
        ]

        with patch.object(settings, "requirement_extraction_llm_v2_enabled", True), patch.object(
            pipeline,
            "_parse_document",
            return_value=elements,
        ):
            stats = await pipeline.ingest_file(
                file_path="rfp.pdf",
                document_id=18,
                doc_type="tender",
                metadata={"tender_id": 18},
            )

        self.assertEqual(stats["requirement_extraction_method"], "heuristic_v1")
        self.assertGreaterEqual(stats["requirements_detected"], 1)
        self.assertEqual(len(stats["warnings"]), 1)
        self.assertEqual(stats["warnings"][0]["code"], "llm_extraction_failed")
        self.assertEqual(stats["warnings"][0]["status_code"], 403)
        self.assertEqual(stats["warnings"][0]["source"], "requirement_extraction_llm_v2")
        self.assertEqual(stats["warnings"][0]["fallback_method"], "heuristic_v1")
        self.assertTrue(stats["warnings"][0]["fallback_applied"])
        self.assertEqual(stats["requirement_scope"], "general")
        self.assertEqual(stats["requirement_extractor_pipeline"], "heuristic_fallback_v1")

    async def test_ingest_file_respects_llm_v2_rollout_percent(self) -> None:
        generator = _FakeGenerator(
            {
                "schema_version": "requirement_extraction_v2.schema.v1",
                "requirements": [
                    {
                        "requirement_text": "The bidder must provide ISO 27001 certification.",
                        "category": "technical",
                        "priority": "high",
                        "confidence": 0.91,
                        "citations": [
                            {
                                "source_reference": "Mandatory Requirements",
                                "quote": "The bidder must provide ISO 27001 certification.",
                            }
                        ],
                    }
                ],
            }
        )
        pipeline = IngestionPipeline(_FakeRagEngine(generator=generator))
        elements = [
            {"type": "Title", "text": "Mandatory Requirements", "metadata": {"section": "Mandatory Requirements"}},
            {
                "type": "Text",
                "text": "The bidder must provide ISO 27001 certification.",
                "metadata": {"page_number": 1},
            },
        ]

        with patch.object(settings, "requirement_extraction_llm_v2_enabled", True), patch.object(
            settings,
            "requirement_extraction_llm_v2_rollout_percent",
            0,
            create=True,
        ), patch.object(
            settings,
            "requirement_extraction_llm_v2_tender_ids",
            "",
            create=True,
        ), patch.object(
            settings,
            "requirement_extraction_llm_v2_blocked_tender_ids",
            "",
            create=True,
        ), patch.object(
            pipeline,
            "_parse_document",
            return_value=elements,
        ):
            stats = await pipeline.ingest_file(
                file_path="rfp.pdf",
                document_id=17,
                doc_type="tender",
                metadata={"tender_id": 17},
            )

        self.assertEqual(stats["requirement_extraction_method"], "heuristic_v1")
        self.assertEqual(generator.calls, [])


if __name__ == "__main__":
    unittest.main()
