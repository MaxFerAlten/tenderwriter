"""Regression and introduction tests for tender document import staging."""

from __future__ import annotations

import io
import os
import sys
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
        self.commit_count = 0
        self.refresh_calls: list[object] = []
        self.added_items: list[object] = []

    def add(self, instance: object) -> None:
        self.added_items.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1
        for item in self.added_items:
            if not getattr(item, "id", None):
                item.id = 999

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_calls.append(instance)


def _build_upload_file() -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"fake tender content"),
        filename="rfp.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


def _build_request() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace())


class TenderImportStagingTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_tender_document_enqueues_task_and_returns_202(self) -> None:
        tender = Tender(id=41, title="Framework Tender", status=TenderStatus.DRAFT)
        current_user = SimpleNamespace(id=7, role="admin", email="mario.rossi@example.com")
        db = _FakeAsyncSession()
        request = _build_request()

        fake_minio_client = Mock()
        fake_minio_client.bucket_exists.return_value = True

        fake_task_result = Mock()
        fake_task_result.id = "celery-abc-123"

        fake_task_module = Mock()
        fake_task_module.index_document_task.delay.return_value = fake_task_result

        with (
            patch.object(_TENDERS_MODULE, "Minio", return_value=fake_minio_client),
            patch.dict(sys.modules, {"app.tasks": fake_task_module}),
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE, "get_tender_upload_path", return_value="tenders/41/rfp.pdf"
            ),
        ):
            response = await import_tender_document(
                tender_id=41,
                request=request,
                file=_build_upload_file(),
                current_user=current_user,
                db=db,
            )

        self.assertEqual(response["message"], "Document uploaded and ingestion queued successfully")
        self.assertEqual(response["status"], "queued")
        self.assertEqual(response["task_id"], "celery-abc-123")
        self.assertEqual(response["tender_id"], 41)

        self.assertEqual(len(db.added_items), 1)
        doc = db.added_items[0]
        self.assertEqual(doc.filename, "rfp.pdf")
        self.assertEqual(doc.tender_id, 41)
        self.assertEqual(doc.ingestion_job_id, "celery-abc-123")
        self.assertGreaterEqual(db.flush_count, 1)
        self.assertGreaterEqual(db.commit_count, 1)

        fake_minio_client.put_object.assert_called_once()
        fake_task_module.index_document_task.delay.assert_called_once_with(999)


if __name__ == "__main__":
    unittest.main()
