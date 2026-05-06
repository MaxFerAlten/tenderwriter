"""Regression tests for unique tender title handling."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

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

TenderCreate = _TENDERS_MODULES.tenders.TenderCreate
TenderUpdate = _TENDERS_MODULES.tenders.TenderUpdate
_ensure_unique_tender_title = _TENDERS_MODULES.tenders._ensure_unique_tender_title
_normalize_tender_title = _TENDERS_MODULES.tenders._normalize_tender_title
create_tender = _TENDERS_MODULES.tenders.create_tender
update_tender = _TENDERS_MODULES.tenders.update_tender

Tender = _TENDERS_MODULES.models.Tender
TenderStatus = _TENDERS_MODULES.models.TenderStatus


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _TenderResult:
    def __init__(self, tender: Tender):
        self._tender = tender

    def scalar_one(self) -> Tender:
        return self._tender


class _TitleCheckSession:
    def __init__(self, scalar_values: list[int | None]) -> None:
        self._scalar_values = list(scalar_values)
        self.executed: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        next_value = self._scalar_values.pop(0) if self._scalar_values else None
        return _ScalarResult(next_value)


class _CreateTenderSession:
    def __init__(self) -> None:
        self.added: Tender | None = None
        self.flush_called = False
        self.refresh_called = False

    def add(self, tender: Tender) -> None:
        self.added = tender

    async def flush(self) -> None:
        self.flush_called = True
        if self.added is not None and self.added.id is None:
            self.added.id = 101

    async def refresh(self, tender: Tender) -> None:
        self.refresh_called = True


class _UpdateTenderSession:
    def __init__(self, tender: Tender) -> None:
        self.tender = tender
        self.flush_called = False
        self.refresh_called = False

    async def execute(self, *_args, **_kwargs):
        return _TenderResult(self.tender)

    async def flush(self) -> None:
        self.flush_called = True

    async def refresh(self, tender: Tender) -> None:
        self.refresh_called = True


class TenderTitleNormalizationTests(unittest.TestCase):
    def test_normalize_tender_title_collapses_whitespace(self) -> None:
        self.assertEqual(_normalize_tender_title("  Tender   Title \n  2026 "), "Tender Title 2026")


class TenderTitleUniquenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_unique_title_check_returns_normalized_title(self) -> None:
        db = _TitleCheckSession([None, None])

        normalized_title = await _ensure_unique_tender_title(db, "  Tender   Unico  ")

        self.assertEqual(normalized_title, "Tender Unico")
        self.assertEqual(len(db.executed), 2)

    async def test_unique_title_check_rejects_case_insensitive_duplicate(self) -> None:
        db = _TitleCheckSession([None, 42])

        with self.assertRaises(HTTPException) as exc:
            await _ensure_unique_tender_title(db, "  TESI  ")

        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(exc.exception.detail, "A tender with this title already exists.")

    async def test_create_tender_uses_normalized_unique_title(self) -> None:
        current_user = type("User", (), {"id": 7, "role": "admin"})()
        db = _CreateTenderSession()

        with (
            patch.object(
                _TENDERS_MODULE,
                "_ensure_unique_tender_title",
                AsyncMock(return_value="Tender Unico"),
            ) as unique_mock,
            patch.object(_TENDERS_MODULE, "ensure_official_chat_room", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_chat_members_from_tender_permissions", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_tender_and_publish_event", AsyncMock()),
        ):
            response = await create_tender(
                data=TenderCreate(title="  Tender   Unico  "),
                current_user=current_user,
                db=db,
            )

        unique_mock.assert_awaited_once_with(db, "  Tender   Unico  ")
        assert db.added is not None
        self.assertEqual(db.added.title, "Tender Unico")
        self.assertTrue(db.flush_called)
        self.assertTrue(db.refresh_called)
        self.assertEqual(response.title, "Tender Unico")

    async def test_update_tender_checks_uniqueness_when_title_changes(self) -> None:
        current_user = type("User", (), {"id": 7, "role": "admin"})()
        tender = Tender(id=13, title="Original title", status=TenderStatus.DRAFT, created_by=7)
        db = _UpdateTenderSession(tender)

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "_ensure_unique_tender_title",
                AsyncMock(return_value="Nuovo titolo"),
            ) as unique_mock,
            patch.object(
                _TENDERS_MODULE, "sync_requirement_compliance_and_gate", AsyncMock(return_value=[])
            ),
            patch.object(_TENDERS_MODULE, "ensure_official_chat_room", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_chat_members_from_tender_permissions", AsyncMock()),
            patch.object(_TENDERS_MODULE, "publish_tender_sync", AsyncMock()),
            patch.object(_TENDERS_MODULE, "publish_domain_event", AsyncMock()),
            patch.object(_TENDERS_MODULE, "sync_tender_and_publish_event", AsyncMock()),
        ):
            response = await update_tender(
                tender_id=13,
                data=TenderUpdate(title="  Nuovo   titolo "),
                current_user=current_user,
                db=db,
            )

        unique_mock.assert_awaited_once_with(db, "  Nuovo   titolo ", exclude_tender_id=13)
        self.assertEqual(tender.title, "Nuovo titolo")
        self.assertTrue(db.flush_called)
        self.assertTrue(db.refresh_called)
        self.assertEqual(response.title, "Nuovo titolo")


if __name__ == "__main__":
    unittest.main()
