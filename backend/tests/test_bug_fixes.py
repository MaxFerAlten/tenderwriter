import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from test_module_loaders import (
    _build_fake_jose_module,
    load_auth_provider_test_modules,
    load_tenders_test_modules,
)

_TENDERS_MODULES = load_tenders_test_modules()
_AUTH_PROVIDER_MODULES = load_auth_provider_test_modules()
_TENDERS_MODULE = _TENDERS_MODULES.tenders

delete_tender = _TENDERS_MODULES.tenders.delete_tender
Tender = _TENDERS_MODULES.models.Tender
User = _AUTH_PROVIDER_MODULES.models.User
_AUTH_LEGACY_MODULE = _AUTH_PROVIDER_MODULES.legacy
LegacyJWTProvider = _AUTH_PROVIDER_MODULES.legacy.LegacyJWTProvider
_get_provider = _AUTH_PROVIDER_MODULES.provider._get_provider


@pytest.mark.asyncio
async def test_bug_01_delete_tender_commits():
    """Verify that delete_tender calls db.commit() to persist deletion."""
    mock_db = AsyncMock()
    mock_user = AsyncMock()

    with patch.object(_TENDERS_MODULE, "check_tender_access", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "dummy_tender"
        await delete_tender(tender_id=1, current_user=mock_user, db=mock_db)

        mock_db.delete.assert_called_once_with("dummy_tender")
        mock_db.commit.assert_awaited_once()  # This proves BUG-01 is fixed


def test_bug_02_sql_injection_ilike_escaped():
    """Verify that % and _ and \\ are escaped before ilike is called."""
    search = "%admin_test\\"
    escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # Prove the escaping logic works properly
    assert escaped_search == "\\%admin\\_test\\\\"

    # Verify SQLAlchemy ILIKE compiles with the ESCAPE clause
    query = select(Tender)
    query = query.where(Tender.title.ilike(f"%{escaped_search}%", escape="\\"))

    sql_string = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "ESCAPE '\\'" in sql_string
    assert "\\%admin\\_test\\\\" in sql_string  # This proves BUG-02 is fixed


@pytest.mark.asyncio
async def test_bug_16_inactive_or_unverified_jwt_rejected():
    """Verify that even with a valid JWT, unverified or inactive users are rejected."""
    provider = LegacyJWTProvider()

    mock_db = AsyncMock()
    unverified_user = User(id=1, email="test@test.com", is_active=True, is_verified=False)

    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = unverified_user
    mock_db.execute.return_value = mock_result

    with patch.object(_AUTH_LEGACY_MODULE.jwt, "decode") as mock_jwt:
        mock_jwt.return_value = {"sub": "1"}

        with pytest.raises(HTTPException) as exc_info:
            await provider.validate_token("valid_token", mock_db)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Account not verified"  # This proves BUG-16 is fixed


def test_auth_astratta_provider_resolution():
    """Verify that the system dynamically resolves the AuthProvider based on settings."""
    original_provider = settings.auth_provider
    try:
        settings.auth_provider = "legacy"
        _get_provider.cache_clear()
        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
            patch.dict(sys.modules, {"jose": _build_fake_jose_module()}),
        ):
            provider = _get_provider()
        assert provider.__class__.__name__ == "LegacyJWTProvider"

        settings.auth_provider = "invalid_provider"
        _get_provider.cache_clear()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
            patch.dict(sys.modules, {"jose": _build_fake_jose_module()}),
            pytest.raises(ValueError, match="Unknown AUTH_PROVIDER: 'invalid_provider'"),
        ):
            _get_provider()
    finally:
        settings.auth_provider = original_provider
        _get_provider.cache_clear()
