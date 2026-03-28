"""
TenderWriter — Auth Provider Registry

Selects the active auth provider based on ``settings.auth_provider``
and exposes the FastAPI dependency ``get_current_user``.

To add a new provider:
  1. Create ``app/auth/my_provider.py`` implementing ``AuthProvider``
  2. Add an entry to ``_PROVIDERS`` below
  3. Set ``AUTH_PROVIDER=my_provider`` in .env
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.auth.base import AuthenticatedUser, AuthProvider
from app.config import settings
from app.db.database import get_db

logger = structlog.get_logger()

# Re-export so routers can keep importing from ``app.auth``
UserResponse = AuthenticatedUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Provider registry ──


@lru_cache(maxsize=1)
def _get_provider() -> AuthProvider:
    """Instantiate the configured auth provider (cached singleton)."""
    provider_name = (settings.auth_provider or "legacy").strip().lower()

    if provider_name == "legacy":
        from app.auth.legacy import LegacyJWTProvider

        return LegacyJWTProvider()

    if provider_name == "keycloak":
        from app.auth.keycloak import KeycloakOIDCProvider

        logger.info("auth.provider_selected", provider="keycloak")
        return KeycloakOIDCProvider()

    if provider_name == "hybrid":
        from app.auth.hybrid import HybridAuthProvider

        logger.info("auth.provider_selected", provider="hybrid")
        return HybridAuthProvider()

    raise ValueError(
        f"Unknown AUTH_PROVIDER: '{provider_name}'. "
        f"Valid values: legacy, keycloak, hybrid"
    )


# ── FastAPI dependency ──


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """Validate the bearer token via the active auth provider."""
    provider = _get_provider()
    return await provider.validate_token(token, db)
