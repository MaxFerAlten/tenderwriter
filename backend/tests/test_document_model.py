"""Tests for the Document model lifecycle extensions.

Validates that:
1. Document can be created with the new tender lifecycle fields
2. Tender.documents relationship works bidirectionally
3. IngestionStatus enum values are accessible
4. source_kind defaults to 'upload'
"""

import os
import sys
import unittest
from datetime import datetime, timezone

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

# Add backend root to sys.path so test_module_loaders is importable
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from test_module_loaders import load_models_test_module

_MODELS = load_models_test_module()

Document = _MODELS.Document
IngestionStatus = _MODELS.IngestionStatus
Tender = _MODELS.Tender
TenderStatus = _MODELS.TenderStatus


class TestDocumentModelFields(unittest.TestCase):
    """Verify the new lifecycle columns exist and accept correct values."""

    def test_document_has_tender_id_column(self) -> None:
        doc = Document(
            filename="test.pdf",
            file_url="minio://bucket/path/test.pdf",
            doc_type="tender",
            tender_id=42,
        )
        self.assertEqual(doc.tender_id, 42)

    def test_document_has_storage_columns(self) -> None:
        doc = Document(
            filename="test.pdf",
            file_url="minio://bucket/path/test.pdf",
            storage_bucket="tw-uploads",
            storage_object_name="tenders/42/test.pdf",
        )
        self.assertEqual(doc.storage_bucket, "tw-uploads")
        self.assertEqual(doc.storage_object_name, "tenders/42/test.pdf")

    def test_document_source_kind_defaults_to_upload(self) -> None:
        # The Python-level default on Column(default="upload") is only applied
        # at flush/insert time, not at construction time.  Verify the column
        # definition carries the intended default.
        col = Document.__table__.columns["source_kind"]
        self.assertEqual(col.default.arg, "upload")

    def test_document_source_kind_can_be_set(self) -> None:
        for kind in ("upload", "onlyoffice", "generated", "library"):
            doc = Document(filename="test.pdf", file_url="url", source_kind=kind)
            self.assertEqual(doc.source_kind, kind)

    def test_document_ingestion_timestamps(self) -> None:
        now = datetime.now(timezone.utc)
        doc = Document(
            filename="test.pdf",
            file_url="url",
            ingestion_started_at=now,
            ingestion_completed_at=now,
        )
        self.assertEqual(doc.ingestion_started_at, now)
        self.assertEqual(doc.ingestion_completed_at, now)

    def test_document_ingestion_job_id(self) -> None:
        doc = Document(
            filename="test.pdf",
            file_url="url",
            ingestion_job_id="celery-task-abc-123",
        )
        self.assertEqual(doc.ingestion_job_id, "celery-task-abc-123")

    def test_document_ingestion_status_enum(self) -> None:
        for status in IngestionStatus:
            doc = Document(
                filename="test.pdf",
                file_url="url",
                ingestion_status=status,
            )
            self.assertEqual(doc.ingestion_status, status)

    def test_document_nullable_tender_id(self) -> None:
        doc = Document(filename="test.pdf", file_url="url", tender_id=None)
        self.assertIsNone(doc.tender_id)


class TestTenderDocumentRelationship(unittest.TestCase):
    """Verify the bidirectional Tender <-> Document relationship exists at the model level."""

    def test_tender_has_documents_attribute(self) -> None:
        tender = Tender(title="Test Tender", status=TenderStatus.DRAFT)
        self.assertTrue(hasattr(tender, "documents"))

    def test_document_has_tender_attribute(self) -> None:
        doc = Document(filename="test.pdf", file_url="url")
        self.assertTrue(hasattr(doc, "tender"))


class TestDocumentFullConstruction(unittest.TestCase):
    """Verify that a Document with all new fields can be constructed without error."""

    def test_full_document_construction(self) -> None:
        now = datetime.now(timezone.utc)
        doc = Document(
            filename="bando_gara_2026.pdf",
            file_url="minio://tw-uploads/tenders/1/bando_gara_2026.pdf",
            doc_type="tender",
            file_size=2_500_000,
            mime_type="application/pdf",
            ingestion_status=IngestionStatus.PENDING,
            chunk_count=0,
            error_message=None,
            metadata_json={"original_filename": "Bando di Gara 2026.pdf"},
            uploaded_by=1,
            tender_id=1,
            storage_bucket="tw-uploads",
            storage_object_name="admin/test-tender/1/bando_gara_2026.pdf",
            source_kind="upload",
            ingestion_started_at=None,
            ingestion_completed_at=None,
            ingestion_job_id=None,
        )
        self.assertEqual(doc.filename, "bando_gara_2026.pdf")
        self.assertEqual(doc.tender_id, 1)
        self.assertEqual(doc.ingestion_status, IngestionStatus.PENDING)
        self.assertEqual(doc.storage_bucket, "tw-uploads")
        self.assertEqual(doc.source_kind, "upload")
        self.assertIsNone(doc.ingestion_started_at)


if __name__ == "__main__":
    unittest.main()
