"""Regression and introduction tests for tender document import staging."""

from __future__ import annotations

import io
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from starlette.datastructures import Headers, UploadFile

from test_module_loaders import load_tenders_test_modules

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

_TENDERS_MODULES = load_tenders_test_modules()
_TENDERS_MODULE = _TENDERS_MODULES.tenders

import_tender_document = _TENDERS_MODULE.import_tender_document
Tender = _TENDERS_MODULES.models.Tender
TenderStatus = _TENDERS_MODULES.models.TenderStatus


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.flush_count = 0
        self.refresh_calls: list[object] = []

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_calls.append(instance)


def _build_upload_file() -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"fake tender content"),
        filename="rfp.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


def _build_request() -> SimpleNamespace:
    rag_engine = SimpleNamespace(ensure_initialized=AsyncMock())
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(rag_engine=rag_engine)))


def _build_fake_pipeline_module(stats: dict[str, object]) -> tuple[types.ModuleType, type]:
    fake_module = types.ModuleType("app.ingestion.pipeline")

    class _FakePipeline:
        ingest_calls: list[dict[str, object]] = []

        def __init__(self, rag_engine) -> None:
            self.rag_engine = rag_engine

        async def ingest_file(self, **kwargs):
            _FakePipeline.ingest_calls.append(kwargs)
            return dict(stats)

    fake_module.IngestionPipeline = _FakePipeline
    return fake_module, _FakePipeline


class TenderImportStagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_tender_document_keeps_requirement_materialization_and_sync(self) -> None:
        tender = Tender(id=41, title="Framework Tender", status=TenderStatus.DRAFT)
        tender.requirements = []
        current_user = SimpleNamespace(id=7, role="admin", email="mario.rossi@example.com")
        db = _FakeAsyncSession()
        request = _build_request()
        requirement_candidates = [
            {"summary": "Provide signed annex A.", "reference": "Section 1", "priority": "high"},
            {
                "summary": "Include an implementation plan with milestones.",
                "reference": "Section 2",
                "priority": "medium",
            },
        ]
        stats = {
            "status": "completed",
            "chunks": 3,
            "entities": 0,
            "point_ids": ["point-1"],
            "requirements_detected": 2,
            "requirement_candidates": requirement_candidates,
            "sections_detected": 2,
        }
        created_requirements = ["req-1", "req-2"]
        fake_pipeline_module, fake_pipeline_class = _build_fake_pipeline_module(stats)

        with (
            patch.dict(sys.modules, {"app.ingestion.pipeline": fake_pipeline_module}),
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(_TENDERS_MODULE, "get_tender_upload_path", return_value="tenders/41/rfp.pdf"),
            patch.object(_TENDERS_MODULE, "stage_extracted_requirement_candidates", AsyncMock(return_value=(None, []))),
            patch.object(_TENDERS_MODULE, "apply_extracted_requirement_candidates", Mock(return_value=created_requirements)) as apply_mock,
            patch.object(_TENDERS_MODULE, "sync_tender_requirements_to_graph", AsyncMock(return_value=2)) as graph_mock,
            patch.object(_TENDERS_MODULE, "sync_requirement_compliance_and_gate", AsyncMock(return_value=[])),
            patch.object(_TENDERS_MODULE, "ensure_official_chat_room", AsyncMock()) as ensure_chat_mock,
            patch.object(_TENDERS_MODULE, "sync_chat_members_from_tender_permissions", AsyncMock()) as sync_chat_mock,
            patch.object(_TENDERS_MODULE, "sync_tender_and_publish_event", AsyncMock()) as sync_event_mock,
            patch.object(_TENDERS_MODULE, "publish_domain_event", AsyncMock()) as publish_event_mock,
        ):
            response = await import_tender_document(
                tender_id=41,
                request=request,
                file=_build_upload_file(),
                current_user=current_user,
                db=db,
            )

        self.assertEqual(response["message"], "Document uploaded and ingested successfully")
        self.assertEqual(response["stats"]["requirements_detected"], 2)
        self.assertEqual(tender.status, TenderStatus.ACTIVE)
        self.assertEqual(fake_pipeline_class.ingest_calls[0]["document_id"], 41)
        apply_mock.assert_called_once_with(tender, requirement_candidates)
        graph_mock.assert_awaited_once()
        self.assertEqual(graph_mock.await_args.args[2], created_requirements)
        ensure_chat_mock.assert_awaited_once()
        sync_chat_mock.assert_awaited_once()
        sync_event_mock.assert_awaited_once()
        self.assertEqual(sync_event_mock.await_args.kwargs["event_type"], "tender_document_ingested")
        publish_event_mock.assert_awaited_once()
        self.assertEqual(publish_event_mock.await_args.kwargs["event_type"], "requirements_extracted")
        self.assertEqual(
            publish_event_mock.await_args.kwargs["payload"]["extracted_candidates"],
            requirement_candidates,
        )
        self.assertEqual(
            publish_event_mock.await_args.kwargs["payload"]["created_requirements"],
            created_requirements,
        )
        self.assertGreaterEqual(db.flush_count, 2)
        self.assertEqual(db.refresh_calls, [tender])

    async def test_import_tender_document_stages_candidates_with_source_provenance(self) -> None:
        tender = Tender(id=42, title="Services Tender", status=TenderStatus.ACTIVE)
        tender.requirements = []
        current_user = SimpleNamespace(id=9, role="admin", email="giulia@example.com")
        db = _FakeAsyncSession()
        request = _build_request()
        requirement_candidates = [
            {"summary": "Provide signed annex A.", "reference": "Section 1", "priority": "high"}
        ]
        stats = {
            "status": "completed",
            "chunks": 1,
            "entities": 0,
            "point_ids": [],
            "requirements_detected": 1,
            "requirement_candidates": requirement_candidates,
            "sections_detected": 1,
            "requirement_extraction_method": "heuristic_v1",
        }
        fake_pipeline_module, _ = _build_fake_pipeline_module(stats)

        with (
            patch.dict(sys.modules, {"app.ingestion.pipeline": fake_pipeline_module}),
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(_TENDERS_MODULE, "get_tender_upload_path", return_value="tenders/42/rfp.pdf"),
            patch.object(_TENDERS_MODULE, "stage_extracted_requirement_candidates", AsyncMock(return_value=(None, []))) as stage_mock,
            patch.object(_TENDERS_MODULE, "apply_extracted_requirement_candidates", Mock(return_value=[])),
            patch.object(_TENDERS_MODULE, "sync_tender_requirements_to_graph", AsyncMock(return_value=0)),
            patch.object(_TENDERS_MODULE, "sync_requirement_compliance_and_gate", AsyncMock(return_value=[])),
            patch.object(_TENDERS_MODULE, "ensure_official_chat_room", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_chat_members_from_tender_permissions", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_tender_and_publish_event", AsyncMock()),
            patch.object(_TENDERS_MODULE, "publish_domain_event", AsyncMock()),
        ):
            await import_tender_document(
                tender_id=42,
                request=request,
                file=_build_upload_file(),
                current_user=current_user,
                db=db,
            )

        stage_mock.assert_awaited_once()
        self.assertEqual(stage_mock.await_args.args[0], db)
        self.assertEqual(stage_mock.await_args.kwargs["tender_id"], 42)
        self.assertEqual(stage_mock.await_args.kwargs["actor_id"], 9)
        self.assertEqual(stage_mock.await_args.kwargs["source_document_ref"], "tenders/42/rfp.pdf")
        self.assertEqual(stage_mock.await_args.kwargs["filename"], "rfp.pdf")
        self.assertEqual(stage_mock.await_args.kwargs["extraction_method"], "heuristic_v1")
        self.assertEqual(stage_mock.await_args.kwargs["candidates"], requirement_candidates)
        self.assertEqual(stage_mock.await_args.kwargs["metadata"]["content_type"], "application/pdf")
        self.assertEqual(stage_mock.await_args.kwargs["metadata"]["requirements_detected"], 1)
        self.assertEqual(stage_mock.await_args.kwargs["metadata"]["sections_detected"], 1)
        self.assertEqual(stage_mock.await_args.kwargs["metadata"]["ingestion_status"], "completed")


if __name__ == "__main__":
    unittest.main()
