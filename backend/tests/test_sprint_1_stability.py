import os
import sys
import types
import unittest
import jwt
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.api.auth import OTPVerify, UserLogin, UserRegister, register, verify_otp
from app.api.onlyoffice import (
    _build_config_dict,
    _build_download_token,
    _build_signed_file_url,
    _validate_callback_token,
    _verify_download_token,
    _verify_file_signature,
)
from app.tasks import generate_proposal_section_task


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class GenerateProposalSectionTaskTests(unittest.TestCase):
    def test_generate_section_task_uses_query_api(self) -> None:
        @dataclass
        class FakeRAGQuery:
            text: str
            mode: object
            section_title: str = ""
            instructions: str = ""
            filters: dict = field(default_factory=dict)

        class FakeQueryMode:
            WRITE_SECTION = "write_section"

        class FakeEngine:
            last_instance = None

            def __init__(self):
                self.initialized = False
                self.shutdown_called = False
                self.query_arg = None
                FakeEngine.last_instance = self

            async def initialize(self):
                self.initialized = True

            async def query(self, rag_query):
                self.query_arg = rag_query
                return SimpleNamespace(answer="Generated section body")

            async def shutdown(self):
                self.shutdown_called = True

        fake_module = types.ModuleType("app.rag.engine")
        fake_module.HybridRAGEngine = FakeEngine
        fake_module.QueryMode = FakeQueryMode
        fake_module.RAGQuery = FakeRAGQuery

        with patch.dict(sys.modules, {"app.rag.engine": fake_module}):
            result = generate_proposal_section_task.run(12, 34, "Write the executive summary")

        engine = FakeEngine.last_instance
        self.assertIsNotNone(engine)
        self.assertTrue(engine.initialized)
        self.assertTrue(engine.shutdown_called)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["content"], "Generated section body")
        self.assertIsInstance(engine.query_arg, FakeRAGQuery)
        self.assertEqual(engine.query_arg.mode, FakeQueryMode.WRITE_SECTION)
        self.assertEqual(engine.query_arg.text, "Write the executive summary")
        self.assertEqual(engine.query_arg.instructions, "Write the executive summary")
        self.assertEqual(engine.query_arg.section_title, "Proposal Section 34")
        self.assertEqual(engine.query_arg.filters["proposal_id"], 12)
        self.assertEqual(engine.query_arg.filters["section_id"], 34)


class VerifyOtpTests(unittest.IsolatedAsyncioTestCase):
    async def test_verify_otp_hides_unknown_user(self) -> None:
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(None)),
            commit=AsyncMock(),
        )

        with self.assertRaises(HTTPException) as ctx:
            await verify_otp.__wrapped__(
                SimpleNamespace(),
                OTPVerify(email="missing@example.com", otp="123456"),
                db,
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid OTP")

    async def test_verify_otp_uses_latest_token_query_and_deletes_all_user_tokens(self) -> None:
        now = datetime.now(timezone.utc)
        user = SimpleNamespace(
            id=7,
            email="editor@example.com",
            name="Editor",
            role="editor",
            is_verified=False,
        )
        otp_record = SimpleNamespace(
            id=99,
            token="654321",
            attempts=0,
            max_attempts=3,
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        )
        db = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _ScalarResult(user),
                    _ScalarResult(otp_record),
                    _ScalarResult(None),
                ]
            ),
            commit=AsyncMock(),
        )

        result = await verify_otp.__wrapped__(
            SimpleNamespace(),
            OTPVerify(email=user.email, otp="654321"),
            db,
        )

        token_select_stmt = db.execute.await_args_list[1].args[0]
        delete_stmt = db.execute.await_args_list[2].args[0]

        self.assertIn("ORDER BY otp_tokens.created_at DESC", str(token_select_stmt))
        self.assertIn("LIMIT", str(token_select_stmt).upper())
        self.assertIn("DELETE FROM otp_tokens", str(delete_stmt))
        self.assertTrue(user.is_verified)
        self.assertEqual(result.user.email, user.email)
        self.assertEqual(result.user.id, user.id)
        self.assertEqual(db.commit.await_count, 1)


class RegisterTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_rolls_back_when_otp_delivery_fails(self) -> None:
        user_records: list[object] = []

        async def flush_side_effect() -> None:
            if user_records:
                user_records[-1].id = 42

        def add_side_effect(instance: object) -> None:
            user_records.append(instance)

        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(None)),
            add=Mock(side_effect=add_side_effect),
            flush=AsyncMock(side_effect=flush_side_effect),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )

        with (
            patch("app.api.auth.send_otp_email", AsyncMock(side_effect=RuntimeError("smtp down"))),
            self.assertRaises(HTTPException) as ctx,
        ):
            await register.__wrapped__(
                SimpleNamespace(),
                UserRegister(email="new@example.com", name="New User", password="secret-pass"),
                db,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Unable to send verification code. Please try again.")
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()


class AuthSchemaValidationTests(unittest.TestCase):
    def test_auth_dtos_require_valid_email_addresses(self) -> None:
        invalid_email = "not-an-email"

        with self.assertRaises(ValidationError):
            UserRegister(email=invalid_email, name="New User", password="secret-pass")

        with self.assertRaises(ValidationError):
            UserLogin(email=invalid_email, password="secret-pass")

        with self.assertRaises(ValidationError):
            OTPVerify(email=invalid_email, otp="123456")


class OnlyOfficeSignedUrlTests(unittest.TestCase):
    def test_onlyoffice_config_forces_a_consistent_ui_theme(self) -> None:
        config = _build_config_dict(
            doc_key="doc-key-123",
            title="Executive Summary.docx",
            file_url="http://backend.test/files/doc-key-123",
            callback_url="http://backend.test/api/onlyoffice/callback",
        )

        self.assertEqual(
            config["editorConfig"]["customization"]["uiTheme"],
            "theme-dark",
        )

    def test_signed_file_url_contains_valid_signature(self) -> None:
        download_token = _build_download_token(doc_key="doc-key-123", user_id=7)
        url = _build_signed_file_url("doc-key-123", download_token=download_token)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertIn("expires", params)
        self.assertIn("signature", params)
        self.assertIn("download_token", params)
        self.assertTrue(
            _verify_file_signature(
                "doc-key-123",
                int(params["expires"][0]),
                params["signature"][0],
            )
        )
        self.assertTrue(
            _verify_download_token(
                "doc-key-123",
                {"owner_user_id": 7},
                params["download_token"][0],
            )
        )

    def test_signed_file_url_rejects_tampered_signature(self) -> None:
        url = _build_signed_file_url(
            "doc-key-123",
            download_token=_build_download_token(doc_key="doc-key-123", user_id=7),
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertFalse(
            _verify_file_signature(
                "doc-key-123",
                int(params["expires"][0]),
                "bad-signature",
            )
        )

    def test_download_token_is_bound_to_document_owner(self) -> None:
        token = _build_download_token(doc_key="doc-key-123", user_id=7)

        self.assertFalse(
            _verify_download_token(
                "doc-key-123",
                {"owner_user_id": 99},
                token,
            )
        )

    def test_callback_token_must_match_document_key(self) -> None:
        callback_token = jwt.encode(
            {"document": {"key": "doc-key-123"}},
            _TEST_ENV["ONLYOFFICE_JWT_SECRET"],
            algorithm="HS256",
        )

        self.assertTrue(_validate_callback_token(callback_token, "doc-key-123"))
        self.assertFalse(_validate_callback_token(callback_token, "other-doc"))


if __name__ == "__main__":
    unittest.main()
