import os
import sys
import types
import unittest
import base64
import importlib.metadata
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from importlib import import_module
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from test_module_loaders import load_models_test_module

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


_AUTH_TEST_MODULE = None
_ONLYOFFICE_TEST_MODULE = None
_TASKS_TEST_MODULE = None


def _build_fake_pyjwt_module():
    fake_jwt = types.ModuleType("jwt")

    class _InvalidTokenError(Exception):
        pass

    def _default(value):
        if hasattr(value, "isoformat"):
            return {"__datetime__": value.isoformat()}
        raise TypeError(f"Unsupported value for fake jwt: {value!r}")

    def _encode(payload, secret, algorithm="HS256"):
        del secret, algorithm
        raw = json.dumps(payload, default=_default).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def _decode(token, secret, algorithms=None):
        del secret, algorithms
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise _InvalidTokenError(str(exc)) from exc

    fake_jwt.encode = _encode
    fake_jwt.decode = _decode
    fake_jwt.InvalidTokenError = _InvalidTokenError
    return fake_jwt


def _build_fake_jose_module():
    fake_jose = types.ModuleType("jose")

    class _JWTError(Exception):
        pass

    fake_jose.JWTError = _JWTError
    fake_jose.jwt = SimpleNamespace(
        encode=lambda payload, secret, algorithm="HS256": _build_fake_pyjwt_module().encode(payload, secret, algorithm),
        decode=lambda token, secret, algorithms=None: _build_fake_pyjwt_module().decode(token, secret, algorithms),
    )
    return fake_jose


def _load_auth_module():
    global _AUTH_TEST_MODULE
    if _AUTH_TEST_MODULE is not None:
        return _AUTH_TEST_MODULE

    load_models_test_module()

    fake_passlib_context = types.ModuleType("passlib.context")

    class _FakeCryptContext:
        def __init__(self, *args, **kwargs):
            pass

        def verify(self, plain, hashed):
            return hashed == f"hashed:{plain}"

        def needs_update(self, hashed):
            del hashed
            return False

        def hash(self, password):
            return f"hashed:{password}"

    fake_passlib_context.CryptContext = _FakeCryptContext

    fake_slowapi = types.ModuleType("slowapi")

    class _FakeLimiter:
        def __init__(self, *args, **kwargs):
            pass

        def limit(self, *args, **kwargs):
            def decorator(func):
                @wraps(func)
                async def wrapper(*f_args, **f_kwargs):
                    return await func(*f_args, **f_kwargs)

                return wrapper

            return decorator

    fake_slowapi.Limiter = _FakeLimiter

    fake_slowapi_util = types.ModuleType("slowapi.util")
    fake_slowapi_util.get_remote_address = lambda *args, **kwargs: "127.0.0.1"

    fake_mattermost = types.ModuleType("app.services.mattermost")

    async def _fake_provision_mm_user_for_tw_user(*args, **kwargs):
        return None

    fake_mattermost.provision_mm_user_for_tw_user = _fake_provision_mm_user_for_tw_user

    fake_email_validator = types.ModuleType("email_validator")

    class _FakeEmailNotValidError(ValueError):
        pass

    def _fake_validate_email(email, check_deliverability=False):
        del check_deliverability
        if not isinstance(email, str) or "@" not in email or "." not in email.split("@", 1)[-1]:
            raise _FakeEmailNotValidError("Invalid email address")
        return SimpleNamespace(
            normalized=email,
            local_part=email.split("@", 1)[0],
        )

    fake_email_validator.EmailNotValidError = _FakeEmailNotValidError
    fake_email_validator.validate_email = _fake_validate_email

    original_version = importlib.metadata.version

    def _fake_version(package_name: str) -> str:
        if package_name == "email-validator":
            return "2.0.0"
        return original_version(package_name)

    fake_jose = _build_fake_jose_module()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch("importlib.metadata.version", side_effect=_fake_version),
        patch("pydantic.networks.version", side_effect=_fake_version, create=True),
        patch.dict(
            sys.modules,
            {
                "jose": fake_jose,
                "passlib.context": fake_passlib_context,
                "slowapi": fake_slowapi,
                "slowapi.util": fake_slowapi_util,
                "app.services.mattermost": fake_mattermost,
                "email_validator": fake_email_validator,
            },
        ),
    ):
        sys.modules.pop("app.api.auth", None)
        _AUTH_TEST_MODULE = import_module("app.api.auth")
        return _AUTH_TEST_MODULE


def _load_tasks_module():
    global _TASKS_TEST_MODULE
    if _TASKS_TEST_MODULE is not None:
        return _TASKS_TEST_MODULE

    fake_config = types.ModuleType("app.config")
    fake_config.settings = SimpleNamespace()

    fake_celery = types.ModuleType("app.celery")

    class _FakeTask:
        def __init__(self, func):
            self.run = func

        def __call__(self, *args, **kwargs):
            return self.run(*args, **kwargs)

    class _FakeCeleryApp:
        def task(self, *args, **kwargs):
            def decorator(func):
                return _FakeTask(func)

            return decorator

    fake_celery.celery_app = _FakeCeleryApp()

    fake_database = types.ModuleType("app.db.database")
    fake_database.async_session_factory = Mock()

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "app.celery": fake_celery,
            "app.db.database": fake_database,
        },
    ):
        sys.modules.pop("app.tasks", None)
        _TASKS_TEST_MODULE = import_module("app.tasks")
        return _TASKS_TEST_MODULE


def _load_onlyoffice_module():
    global _ONLYOFFICE_TEST_MODULE
    if _ONLYOFFICE_TEST_MODULE is not None:
        return _ONLYOFFICE_TEST_MODULE

    fake_config = types.ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        minio_bucket="test-bucket",
        minio_endpoint="minio:9000",
        minio_access_key="minio-access",
        minio_secret_key="minio-secret",
        minio_secure=False,
        onlyoffice_ui_theme="theme-dark",
        onlyoffice_jwt_secret=_TEST_ENV["ONLYOFFICE_JWT_SECRET"],
        onlyoffice_file_token_ttl_seconds=300,
        backend_public_url="http://backend.test",
        onlyoffice_url="http://onlyoffice.test",
        onlyoffice_internal_url="http://onlyoffice-internal.test",
    )

    fake_jwt = _build_fake_pyjwt_module()

    fake_docx = types.ModuleType("docx")

    class _FakeDocxDocument:
        def __init__(self, *args, **kwargs):
            self.paragraphs = []

        def add_paragraph(self, text=""):
            paragraph = SimpleNamespace(text=text, runs=[SimpleNamespace(font=SimpleNamespace(size=None))])
            self.paragraphs.append(paragraph)
            return paragraph

        def save(self, target):
            if hasattr(target, "write"):
                target.write(b"")

    fake_docx.Document = _FakeDocxDocument

    fake_docx_shared = types.ModuleType("docx.shared")
    fake_docx_shared.Pt = lambda value: value

    fake_minio = types.ModuleType("minio")

    class _FakeMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket_name):
            return True

        def make_bucket(self, bucket_name):
            return None

        def get_object(self, bucket_name, object_name):
            return SimpleNamespace(read=lambda: b"", close=lambda: None, release_conn=lambda: None)

        def put_object(self, *args, **kwargs):
            return None

        def remove_object(self, *args, **kwargs):
            return None

    fake_minio.Minio = _FakeMinio

    fake_minio_error = types.ModuleType("minio.error")

    class _FakeS3Error(Exception):
        def __init__(self, code="GenericError"):
            super().__init__(code)
            self.code = code

    fake_minio_error.S3Error = _FakeS3Error

    fake_db_database = types.ModuleType("app.db.database")

    async def _fake_get_db():
        return None

    fake_db_database.get_db = _fake_get_db

    fake_db_redis = types.ModuleType("app.db.redis")
    fake_db_redis.redis_client = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
        setex=AsyncMock(),
        delete=AsyncMock(),
    )

    fake_models = types.ModuleType("app.models")
    fake_models.Proposal = type("Proposal", (), {})
    fake_models.ProposalSection = type("ProposalSection", (), {})
    fake_models.ContentBlock = type("ContentBlock", (), {})

    fake_auth = types.ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return SimpleNamespace(id=1, name="Tester", email="tester@test.local")

    class _FakeUserResponse:
        pass

    fake_auth.get_current_user = _fake_get_current_user
    fake_auth.UserResponse = _FakeUserResponse

    fake_naming = types.ModuleType("app.utils.naming")
    fake_naming.sanitize_name = lambda value: value
    fake_naming.get_structured_minio_path = lambda *args, **kwargs: "structured/object.docx"

    fake_compliance = types.ModuleType("app.services.compliance_observability")

    async def _fake_sync_requirement_compliance_and_gate(*args, **kwargs):
        return None

    fake_compliance.sync_requirement_compliance_and_gate = _fake_sync_requirement_compliance_and_gate

    fake_kpi = types.ModuleType("app.services.kpi_reason_engine")
    fake_kpi.build_proposal_section_updated_event_payload = lambda *args, **kwargs: {}

    async def _fake_publish_domain_event(*args, **kwargs):
        return None

    async def _fake_sync_tender_and_publish_event(*args, **kwargs):
        return None

    fake_kpi.publish_domain_event = _fake_publish_domain_event
    fake_kpi.sync_tender_and_publish_event = _fake_sync_tender_and_publish_event

    with patch.dict(
        sys.modules,
        {
            "app.config": fake_config,
            "jwt": fake_jwt,
            "docx": fake_docx,
            "docx.shared": fake_docx_shared,
            "minio": fake_minio,
            "minio.error": fake_minio_error,
            "app.db.database": fake_db_database,
            "app.db.redis": fake_db_redis,
            "app.models": fake_models,
            "app.api.auth": fake_auth,
            "app.utils.naming": fake_naming,
            "app.services.compliance_observability": fake_compliance,
            "app.services.kpi_reason_engine": fake_kpi,
        },
    ):
        sys.modules.pop("app.api.onlyoffice", None)
        _ONLYOFFICE_TEST_MODULE = import_module("app.api.onlyoffice")
        return _ONLYOFFICE_TEST_MODULE


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class GenerateProposalSectionTaskTests(unittest.TestCase):
    def test_generate_section_task_uses_query_api(self) -> None:
        tasks_module = _load_tasks_module()

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
            result = tasks_module.generate_proposal_section_task.run(
                SimpleNamespace(retry=Mock()),
                12,
                34,
                "Write the executive summary",
            )

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
        auth_module = _load_auth_module()
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult(None)),
            commit=AsyncMock(),
        )
        background_tasks = SimpleNamespace(add_task=Mock())

        with self.assertRaises(HTTPException) as ctx:
            await auth_module.verify_otp.__wrapped__(
                SimpleNamespace(),
                auth_module.OTPVerify(email="missing@example.com", otp="123456"),
                background_tasks,
                db,
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid OTP")

    async def test_verify_otp_uses_latest_token_query_and_deletes_all_user_tokens(self) -> None:
        auth_module = _load_auth_module()
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
        background_tasks = SimpleNamespace(add_task=Mock())

        result = await auth_module.verify_otp.__wrapped__(
            SimpleNamespace(),
            auth_module.OTPVerify(email=user.email, otp="654321"),
            background_tasks,
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
        background_tasks.add_task.assert_called_once()


class RegisterTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_rolls_back_when_otp_delivery_fails(self) -> None:
        auth_module = _load_auth_module()
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
            patch.object(auth_module, "send_otp_email", AsyncMock(side_effect=RuntimeError("smtp down"))),
            self.assertRaises(HTTPException) as ctx,
        ):
            await auth_module.register.__wrapped__(
                SimpleNamespace(),
                auth_module.UserRegister(
                    email="new@example.com",
                    name="New User",
                    password="secret-pass",
                ),
                db,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Unable to send verification code. Please try again.")
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()


class AuthSchemaValidationTests(unittest.TestCase):
    def test_auth_dtos_require_valid_email_addresses(self) -> None:
        auth_module = _load_auth_module()
        invalid_email = "not-an-email"

        with self.assertRaises(ValidationError):
            auth_module.UserRegister(
                email=invalid_email,
                name="New User",
                password="secret-pass",
            )

        with self.assertRaises(ValidationError):
            auth_module.UserLogin(email=invalid_email, password="secret-pass")

        with self.assertRaises(ValidationError):
            auth_module.OTPVerify(email=invalid_email, otp="123456")


class OnlyOfficeSignedUrlTests(unittest.TestCase):
    def test_onlyoffice_config_forces_a_consistent_ui_theme(self) -> None:
        onlyoffice_module = _load_onlyoffice_module()
        config = onlyoffice_module._build_config_dict(
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
        onlyoffice_module = _load_onlyoffice_module()
        download_token = onlyoffice_module._build_download_token(doc_key="doc-key-123", user_id=7)
        url = onlyoffice_module._build_signed_file_url("doc-key-123", download_token=download_token)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertIn("expires", params)
        self.assertIn("signature", params)
        self.assertIn("download_token", params)
        self.assertTrue(
            onlyoffice_module._verify_file_signature(
                "doc-key-123",
                int(params["expires"][0]),
                params["signature"][0],
            )
        )
        self.assertTrue(
            onlyoffice_module._verify_download_token(
                "doc-key-123",
                {"owner_user_id": 7},
                params["download_token"][0],
            )
        )

    def test_signed_file_url_rejects_tampered_signature(self) -> None:
        onlyoffice_module = _load_onlyoffice_module()
        url = onlyoffice_module._build_signed_file_url(
            "doc-key-123",
            download_token=onlyoffice_module._build_download_token(doc_key="doc-key-123", user_id=7),
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        self.assertFalse(
            onlyoffice_module._verify_file_signature(
                "doc-key-123",
                int(params["expires"][0]),
                "bad-signature",
            )
        )

    def test_download_token_is_bound_to_document_owner(self) -> None:
        onlyoffice_module = _load_onlyoffice_module()
        token = onlyoffice_module._build_download_token(doc_key="doc-key-123", user_id=7)

        self.assertFalse(
            onlyoffice_module._verify_download_token(
                "doc-key-123",
                {"owner_user_id": 99},
                token,
            )
        )

    def test_callback_token_must_match_document_key(self) -> None:
        onlyoffice_module = _load_onlyoffice_module()
        callback_token = onlyoffice_module.jwt.encode(
            {"document": {"key": "doc-key-123"}},
            _TEST_ENV["ONLYOFFICE_JWT_SECRET"],
            algorithm="HS256",
        )

        self.assertTrue(onlyoffice_module._validate_callback_token(callback_token, "doc-key-123"))
        self.assertFalse(onlyoffice_module._validate_callback_token(callback_token, "other-doc"))


if __name__ == "__main__":
    unittest.main()
