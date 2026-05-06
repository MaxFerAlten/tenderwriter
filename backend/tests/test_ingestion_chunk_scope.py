"""Regression tests for scoped chunk metadata during document ingestion."""

from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

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

if "pydantic_settings" not in sys.modules:
    fake_pydantic_settings = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        def __init__(self, **kwargs) -> None:
            annotations: dict[str, object] = {}
            for cls in reversed(self.__class__.mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for field_name in annotations:
                env_name = field_name.upper()
                if field_name in kwargs:
                    value = kwargs[field_name]
                elif env_name in os.environ:
                    value = os.environ[env_name]
                else:
                    value = getattr(self.__class__, field_name, None)
                setattr(self, field_name, value)

    fake_pydantic_settings.BaseSettings = _BaseSettings
    sys.modules["pydantic_settings"] = fake_pydantic_settings

if "pydantic" not in sys.modules:
    fake_pydantic = types.ModuleType("pydantic")

    def _model_validator(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    fake_pydantic.model_validator = _model_validator
    sys.modules["pydantic"] = fake_pydantic

if "structlog" not in sys.modules:
    fake_structlog = types.ModuleType("structlog")

    class _FakeLogger:
        def info(self, *args, **kwargs) -> None:
            del args, kwargs

        def warning(self, *args, **kwargs) -> None:
            del args, kwargs

        def debug(self, *args, **kwargs) -> None:
            del args, kwargs

        def error(self, *args, **kwargs) -> None:
            del args, kwargs

    fake_structlog.get_logger = lambda *args, **kwargs: _FakeLogger()
    sys.modules["structlog"] = fake_structlog

if "app.services.tender_document_requirement_extractor" not in sys.modules:
    fake_extractor_module = types.ModuleType("app.services.tender_document_requirement_extractor")

    class _FakeExtractionResult:
        def __init__(self, candidates):
            self.candidates = list(candidates or [])
            self.extraction_method = "heuristic_v1"
            self.warnings = []
            self.requirement_scope = "general"
            self.extractor_pipeline = "heuristic_fallback_v1"

    async def _extract_tender_participation_requirements(
        *,
        fallback_candidates=None,
        **kwargs,
    ):
        del kwargs
        return _FakeExtractionResult(fallback_candidates)

    fake_extractor_module.extract_tender_participation_requirements = (
        _extract_tender_participation_requirements
    )
    sys.modules["app.services.tender_document_requirement_extractor"] = fake_extractor_module

if "fastapi.concurrency" not in sys.modules:
    fake_fastapi = types.ModuleType("fastapi")
    fake_fastapi_concurrency = types.ModuleType("fastapi.concurrency")

    async def _run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    fake_fastapi_concurrency.run_in_threadpool = _run_in_threadpool
    sys.modules["fastapi"] = fake_fastapi
    sys.modules["fastapi.concurrency"] = fake_fastapi_concurrency

from app.config import settings
from app.ingestion.pipeline import IngestionPipeline
from app.rag.chunker import ChunkMetadata, TextChunk


class _CapturingRagEngine:
    def __init__(self) -> None:
        self.generator = None
        self.chunk_calls: list[tuple[str, ChunkMetadata]] = []
        self.index_calls: list[list[TextChunk]] = []

    def chunk_and_embed(self, text: str, metadata: ChunkMetadata) -> list[TextChunk]:
        self.chunk_calls.append((text, metadata))
        return [TextChunk(text=text, metadata=metadata)]

    def index_chunks(self, chunks: list[TextChunk]) -> list[str]:
        self.index_calls.append(chunks)
        return [f"point-{index}" for index, _ in enumerate(chunks)]


class IngestionChunkScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_file_groups_chunks_by_page_and_preserves_scope_metadata(self) -> None:
        rag_engine = _CapturingRagEngine()
        pipeline = IngestionPipeline(rag_engine)
        elements = [
            {"type": "Title", "text": "Scope", "metadata": {"page_number": 1}},
            {
                "type": "Text",
                "text": "The supplier must provide a delivery schedule.",
                "metadata": {"page_number": 1},
            },
            {
                "type": "Text",
                "text": "The supplier must maintain ISO 27001 certification.",
                "metadata": {"page_number": 2},
            },
        ]

        with patch.object(pipeline, "_parse_document", return_value=elements):
            stats = await pipeline.ingest_file(
                file_path="/tmp/tender.pdf",
                document_id=17,
                doc_type="tender",
                metadata={
                    "tender_id": 88,
                    "original_filename": "tender.pdf",
                    "source_document_ref": "tenders/88/tender.pdf",
                },
            )

        self.assertEqual(stats["chunks"], 2)
        self.assertEqual(len(rag_engine.chunk_calls), 2)

        first_text, first_meta = rag_engine.chunk_calls[0]
        second_text, second_meta = rag_engine.chunk_calls[1]

        self.assertIn("delivery schedule", first_text)
        self.assertIn("ISO 27001", second_text)
        self.assertEqual(first_meta.document_id, 17)
        self.assertEqual(first_meta.tender_id, 88)
        self.assertEqual(first_meta.section_title, "Scope")
        self.assertEqual(first_meta.page_number, 1)
        self.assertEqual(first_meta.filename, "tender.pdf")
        self.assertEqual(first_meta.source_document_ref, "tenders/88/tender.pdf")
        self.assertEqual(second_meta.page_number, 2)
        self.assertEqual(
            [chunk.metadata.chunk_index for chunk in rag_engine.index_calls[0]], [0, 1]
        )

    async def test_ingest_file_emits_stage_progress_events(self) -> None:
        rag_engine = _CapturingRagEngine()
        pipeline = IngestionPipeline(rag_engine)
        elements = [
            {"type": "Title", "text": "Scope", "metadata": {"page_number": 1}},
            {
                "type": "Text",
                "text": "The supplier must provide a delivery schedule.",
                "metadata": {"page_number": 1},
            },
        ]
        events: list[dict] = []

        async def capture_progress(event: dict) -> None:
            events.append(event)

        with (
            patch.object(settings, "requirement_extraction_llm_v2_enabled", False),
            patch.object(
                pipeline,
                "_parse_document",
                return_value=elements,
            ),
        ):
            await pipeline.ingest_file(
                file_path="/tmp/tender.pdf",
                document_id=19,
                doc_type="tender",
                metadata={"tender_id": 91},
                progress_callback=capture_progress,
            )

        stage_statuses = [(event["stage"], event["status"]) for event in events]
        self.assertEqual(
            stage_statuses,
            [
                ("parse", "started"),
                ("parse", "completed"),
                ("requirement_extraction", "started"),
                ("requirement_extraction", "completed"),
                ("chunking", "started"),
                ("chunking", "completed"),
                ("index_qdrant", "started"),
                ("index_qdrant", "completed"),
            ],
        )
        self.assertEqual(events[1]["stats"]["elements_detected"], 2)
        self.assertEqual(events[3]["stats"]["extraction_method"], "heuristic_v1")
        self.assertEqual(events[5]["stats"]["chunks_created"], 1)
        self.assertEqual(events[7]["stats"]["points_indexed"], 1)

    def test_build_chunk_inputs_marks_logical_procedure_boundaries(self) -> None:
        rag_engine = _CapturingRagEngine()
        pipeline = IngestionPipeline(rag_engine)
        elements = [
            {
                "type": "Title",
                "text": "Gara 040961/2024 - Sistema Cloud Toscano",
                "metadata": {"page_number": 1},
            },
            {
                "type": "Text",
                "text": "Il fornitore deve garantire la gestione del CCTT.",
                "metadata": {"page_number": 1},
            },
            {
                "type": "Title",
                "text": "Gara 012942/2025 - OSCAT DevSecOps",
                "metadata": {"page_number": 11},
            },
            {
                "type": "Text",
                "text": "Il servizio deve includere pipeline GitLab e vulnerability assessment.",
                "metadata": {"page_number": 11},
            },
        ]

        chunk_inputs = pipeline._build_chunk_inputs(
            elements,
            file_path="/tmp/toscana.pdf",
            document_id=25,
            doc_type="tender",
            metadata={"tender_id": 900},
            fallback_text="",
        )

        self.assertEqual(len(chunk_inputs), 2)
        first_meta = chunk_inputs[0][1]
        second_meta = chunk_inputs[1][1]
        self.assertEqual(
            first_meta.extra["procedure_label"],
            "Gara 040961/2024 - Sistema Cloud Toscano",
        )
        self.assertEqual(
            second_meta.extra["procedure_label"],
            "Gara 012942/2025 - OSCAT DevSecOps",
        )
        self.assertNotEqual(first_meta.extra["procedure_key"], second_meta.extra["procedure_key"])

    def test_build_chunk_inputs_keeps_structured_tables_as_dedicated_chunks(self) -> None:
        rag_engine = _CapturingRagEngine()
        pipeline = IngestionPipeline(rag_engine)
        elements = [
            {"type": "Title", "text": "SLA e penali", "metadata": {"page_number": 4}},
            {
                "type": "Text",
                "text": "Il servizio deve rispettare i livelli minimi.",
                "metadata": {"page_number": 4},
            },
            {
                "type": "Table",
                "text": "Ritardo | Penale\n15 giorni | risoluzione",
                "metadata": {
                    "page_number": 4,
                    "is_table": True,
                    "text_as_html": "<table><tr><td>15 giorni</td></tr></table>",
                },
            },
            {
                "type": "Text",
                "text": "La verifica finale chiude la fase.",
                "metadata": {"page_number": 4},
            },
        ]

        chunk_inputs = pipeline._build_chunk_inputs(
            elements,
            file_path="/tmp/capitolato.pdf",
            document_id=26,
            doc_type="tender",
            metadata={"tender_id": 901},
            fallback_text="",
        )

        self.assertEqual(len(chunk_inputs), 3)
        table_text, table_meta = chunk_inputs[1]
        self.assertIn("15 giorni", table_text)
        self.assertTrue(table_meta.extra["is_table"])
        self.assertEqual(
            table_meta.extra["table_html"],
            "<table><tr><td>15 giorni</td></tr></table>",
        )

    def test_build_chunk_inputs_attaches_numeric_mentions_and_parse_warnings(self) -> None:
        rag_engine = _CapturingRagEngine()
        pipeline = IngestionPipeline(rag_engine)
        elements = [
            {"type": "Title", "text": "Fasi e penali", "metadata": {"page_number": 8}},
            {
                "type": "Text",
                "text": "La fase deve concludersi entro 180 giorni con penale Euro 100/giorno.",
                "metadata": {"page_number": 8},
            },
            {
                "type": "Text",
                "text": "Un frammento OCR indica solo entro giorni.",
                "metadata": {"page_number": 8},
            },
        ]

        chunk_inputs = pipeline._build_chunk_inputs(
            elements,
            file_path="/tmp/capitolato.pdf",
            document_id=27,
            doc_type="tender",
            metadata={"tender_id": 902},
            fallback_text="",
        )

        self.assertEqual(len(chunk_inputs), 1)
        extra = chunk_inputs[0][1].extra
        self.assertIn("180 giorni", extra["numeric_mentions"])
        self.assertIn("Euro 100", extra["numeric_mentions"])
        self.assertIn("broken_numeric_fragment", extra["parse_warnings"])


if __name__ == "__main__":
    unittest.main()
