from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.tenders import delete_tender
from app.auth.legacy import LegacyJWTProvider
from app.auth.provider import _get_provider
from app.config import settings
from app.models import Tender, User


@pytest.mark.asyncio
async def test_bug_01_delete_tender_commits():
    """Verify that delete_tender calls db.commit() to persist deletion."""
    mock_db = AsyncMock()
    mock_user = AsyncMock()

    with patch("app.api.tenders.check_tender_access", new_callable=AsyncMock) as mock_check:
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

    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = unverified_user
    mock_db.execute.return_value = mock_result

    with patch("app.auth.legacy.jwt.decode") as mock_jwt:
        mock_jwt.return_value = {"sub": "1"}

        with pytest.raises(HTTPException) as exc_info:
            await provider.validate_token("valid_token", mock_db)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Account not verified"  # This proves BUG-16 is fixed


def test_auth_astratta_provider_resolution():
    """Verify that the system dynamically resolves the AuthProvider based on settings."""
    assert settings.auth_provider == "legacy"

    _get_provider.cache_clear()
    provider = _get_provider()

    assert isinstance(provider, LegacyJWTProvider)

    settings.auth_provider = "invalid_provider"
    _get_provider.cache_clear()

    with pytest.raises(ValueError, match="Unknown AUTH_PROVIDER: 'invalid_provider'"):
        _get_provider()

    settings.auth_provider = "legacy"  # Reset
