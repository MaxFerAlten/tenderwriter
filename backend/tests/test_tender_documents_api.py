"""Tests for the tender documents APIs."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

list_tender_documents = _TENDERS_MODULE.list_tender_documents
get_tender_document = _TENDERS_MODULE.get_tender_document
activate_tender = _TENDERS_MODULE.activate_tender
Tender = _TENDERS_MODULES.models.Tender
TenderStatus = _TENDERS_MODULES.models.TenderStatus
Document = _TENDERS_MODULES.models.Document


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.flush_count = 0
        self.commit_count = 0
        self.refresh_calls: list[object] = []

    async def execute(self, *args, **kwargs) -> object:
        pass

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, instance: object) -> None:
        self.refresh_calls.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1


class TenderDocumentsApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_tender_documents(self) -> None:
        tender = Tender(id=42, title="Test Tender")
        current_user = SimpleNamespace(id=1, role="admin", email="admin@example.com")
        db = _FakeAsyncSession()

        doc1 = Document(id=1, filename="doc1.pdf")
        doc2 = Document(id=2, filename="doc2.pdf")

        # Mock result for scalars().all()
        fake_result = Mock()
        fake_result.scalars.return_value.all.return_value = [doc1, doc2]

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(db, "execute", AsyncMock(return_value=fake_result)),
        ):
            documents = await list_tender_documents(tender_id=42, current_user=current_user, db=db)

        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].filename, "doc1.pdf")
        self.assertEqual(documents[1].filename, "doc2.pdf")

    async def test_get_tender_document(self) -> None:
        tender = Tender(id=42, title="Test Tender")
        current_user = SimpleNamespace(id=1, role="admin", email="admin@example.com")
        db = _FakeAsyncSession()

        doc = Document(id=99, filename="doc_specific.pdf")

        # Mock result for scalar_one_or_none()
        fake_result = Mock()
        fake_result.scalar_one_or_none.return_value = doc

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(db, "execute", AsyncMock(return_value=fake_result)),
        ):
            result = await get_tender_document(tender_id=42, document_id=99, current_user=current_user, db=db)

        self.assertEqual(result.filename, "doc_specific.pdf")

    async def test_activate_tender(self) -> None:
        tender = Tender(id=42, status=TenderStatus.DRAFT)
        current_user = SimpleNamespace(id=1, role="admin", email="admin@example.com")
        db = _FakeAsyncSession()

        fake_result = Mock()
        fake_result.scalar_one.return_value = tender

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(db, "execute", AsyncMock(return_value=fake_result)),
            patch.object(_TENDERS_MODULE, "ensure_official_chat_room", AsyncMock()) as chat_mock,
            patch.object(_TENDERS_MODULE, "sync_chat_members_from_tender_permissions", AsyncMock()) as sync_chat_mock,
            patch.object(_TENDERS_MODULE, "publish_tender_sync", AsyncMock()) as publish_sync_mock,
            patch.object(_TENDERS_MODULE, "_tender_to_response", Mock(return_value={"id": 42, "status": "active"}))
        ):
            response = await activate_tender(tender_id=42, current_user=current_user, db=db)

        self.assertEqual(response["status"], "active")
        self.assertEqual(tender.status, TenderStatus.ACTIVE)
        chat_mock.assert_awaited_once_with(db, tender_id=42, actor_id=1, open_now=True)
        sync_chat_mock.assert_awaited_once_with(db, tender_id=42, actor_id=1)
        publish_sync_mock.assert_awaited_once_with(db, tender_id=42, actor_id=1)
        self.assertGreaterEqual(db.flush_count, 1)

if __name__ == "__main__":
    unittest.main()
