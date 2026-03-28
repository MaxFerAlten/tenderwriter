"""
TenderWriter — Hybrid Auth Provider

Accepts both legacy app-issued JWTs and Keycloak OIDC tokens.
Used when ``AUTH_PROVIDER=hybrid`` so users can authenticate with either:
1. The traditional email/password flow
2. Keycloak SSO
"""

from __future__ import annotations

import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.auth.base import AuthenticatedUser
from app.auth.keycloak import KeycloakOIDCProvider
from app.auth.legacy import LegacyJWTProvider
from app.config import settings

logger = structlog.get_logger()


def _peek_issuer(token: str) -> str | None:
    try:
        payload = pyjwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except Exception:
        return None

    issuer = payload.get("iss")
    return str(issuer) if issuer else None


def _looks_like_keycloak_token(token: str) -> bool:
    issuer = _peek_issuer(token)
    if not issuer:
        return False

    expected_public_issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
    expected_internal_issuer = f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}"
    return issuer in {expected_public_issuer, expected_internal_issuer}


def _looks_like_legacy_token(token: str) -> bool:
    try:
        header = pyjwt.get_unverified_header(token)
    except Exception:
        return False

    return str(header.get("alg", "")).upper() == "HS256"


class HybridAuthProvider:
    """Validate either legacy JWTs or Keycloak OIDC tokens."""

    def __init__(self) -> None:
        self._legacy = LegacyJWTProvider()
        self._keycloak = KeycloakOIDCProvider()

    async def validate_token(
        self,
        token: str,
        db: AsyncSession,
    ) -> AuthenticatedUser:
        if _looks_like_keycloak_token(token):
            return await self._keycloak.validate_token(token, db)

        if _looks_like_legacy_token(token):
            return await self._legacy.validate_token(token, db)

        last_error: HTTPException | None = None
        for provider in (self._legacy, self._keycloak):
            try:
                return await provider.validate_token(token, db)
            except HTTPException as exc:
                last_error = exc

        logger.warning("auth.hybrid_token_unrecognized")
        if last_error:
            raise last_error

        raise HTTPException(status_code=401, detail="Could not validate credentials")
