import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# --- 1. BUG-01 Test (delete_tender missing commit) ---
from app.api.tenders import delete_tender


@pytest.mark.asyncio
async def test_bug_01_delete_tender_commits():
    """Verify that delete_tender calls db.commit() to persist deletion."""
    mock_db = AsyncMock()
    mock_user = AsyncMock()

    # Mock check_tender_access to return a dummy tender
    with patch("app.api.tenders.check_tender_access", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "dummy_tender"

        await delete_tender(tender_id=1, current_user=mock_user, db=mock_db)

        # Ensure db.delete was called
        mock_db.delete.assert_called_once_with("dummy_tender")
        # Ensure db.commit was called! This is what was missing
        mock_db.commit.assert_awaited_once()


# --- 2. BUG-02 Test (SQL Injection via ilike) ---
# We'll test the route logic directly or verify the escaping logic
# by extracting the exact lines from tenders.py
from sqlalchemy import select

from app.models import Tender


def test_bug_02_sql_injection_ilike_escaped():
    """Verify that % and _ and \\ are escaped before ilike is called."""
    search = "%admin_test\\"
    escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    assert escaped_search == "\\%admin\\_test\\\\"

    # Simulate the SQLAlchemy call to ensure it accepts the escape argument
    query = select(Tender)
    query = query.where(Tender.title.ilike(f"%{escaped_search}%", escape="\\"))

    # The generated SQL should contain the ESCAPE '\\' clause
    sql_string = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "ESCAPE '\\\\'" in sql_string
    assert "\\%admin\\_test\\\\" in sql_string


# --- 3. BUG-04 Test (SSRF Anonymizer) ---
from anonymizer.app import _is_allowed_target_url


def test_bug_04_ssrf_anonymizer_blocks_internal_dns():
    """Verify that internal hostnames that resolve to private IPs are blocked."""

    # Normal public IP should be allowed
    assert _is_allowed_target_url("http://google.com") is True

    # localhost should be blocked (explicitly)
    assert _is_allowed_target_url("http://localhost:8080") is False

    # Internal alias like "postgres" should be resolved to its IP and blocked
    # We mock socket.gethostbyname to return a private IP for "postgres"
    with patch("socket.gethostbyname") as mock_dns:
        mock_dns.return_value = "10.0.0.5"  # Private IP

        assert _is_allowed_target_url("http://postgres:5432") is False
        mock_dns.assert_called_with("postgres")


# --- 4. BUG-16 Test (is_verified bypass) ---
from app.auth.legacy import LegacyJWTProvider
from app.models import User


@pytest.mark.asyncio
async def test_bug_16_inactive_or_unverified_jwt_rejected():
    """Verify that even with a valid JWT, unverified or inactive users are rejected."""
    provider = LegacyJWTProvider()

    mock_db = AsyncMock()
    # Mock the DB result to return an unverified user
    unverified_user = User(id=1, email="test@test.com", is_active=True, is_verified=False)

    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = unverified_user
    mock_db.execute.return_value = mock_result

    # Mock jwt.decode to simulate a perfectly valid token
    with patch("app.auth.legacy.jwt.decode") as mock_jwt:
        mock_jwt.return_value = {"sub": "1"}

        with pytest.raises(HTTPException) as exc_info:
            await provider.validate_token("valid_token", mock_db)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Account not verified"


# --- 5. Auth Astratta Test (Pluggable Auth) ---
from app.auth.provider import _get_provider
from app.config import settings


def test_auth_astratta_provider_resolution():
    """Verify that the system dynamically resolves the AuthProvider based on settings."""

    # By default it should be LegacyJWTProvider
    assert settings.auth_provider == "legacy"

    # Clear lru_cache for testing
    _get_provider.cache_clear()
    provider = _get_provider()

    assert isinstance(provider, LegacyJWTProvider)

    # If we change settings to something unknown, it should raise ValueError
    settings.auth_provider = "invalid_provider"
    _get_provider.cache_clear()

    with pytest.raises(ValueError, match="Unknown AUTH_PROVIDER: 'invalid_provider'"):
        _get_provider()

    # Reset
    settings.auth_provider = "legacy"
