"""
TenderWriter — Keycloak OIDC Auth Provider

Validates Keycloak-issued JWT tokens using JWKS (public key verification).
Implements auto-provisioning: if a Keycloak user doesn't exist in the local
database, creates a TenderWriter account automatically.
"""

from __future__ import annotations

import jwt as pyjwt
import structlog
from fastapi import HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import InvalidAudienceError, InvalidTokenError, PyJWKClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthenticatedUser
from app.config import settings
from app.models import User

logger = structlog.get_logger()

# JWKS client — lazy initialized, cached
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client (cached singleton)."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = (
            f"{settings.keycloak_internal_url}/realms/{settings.keycloak_realm}"
            f"/protocol/openid-connect/certs"
        )
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        logger.info("keycloak.jwks_client_created", jwks_url=jwks_url)
    return _jwks_client


def _token_matches_client(payload: dict) -> bool:
    """Accept tokens targeted at this client via aud or azp."""
    audience = payload.get("aud")
    authorized_party = payload.get("azp")

    if isinstance(audience, str) and audience == settings.keycloak_client_id:
        return True
    if isinstance(audience, list) and settings.keycloak_client_id in audience:
        return True
    return isinstance(authorized_party, str) and authorized_party == settings.keycloak_client_id


class KeycloakOIDCProvider:
    """Auth provider that validates Keycloak OIDC tokens via JWKS.

    Token validation:
    1. Fetches the signing key from Keycloak JWKS endpoint
    2. Verifies the JWT signature, expiry, issuer, and audience
    3. Extracts user identity from standard OIDC claims
    4. Looks up or auto-provisions the user in the local database
    """

    async def validate_token(
        self,
        token: str,
        db: AsyncSession,
    ) -> AuthenticatedUser:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate Keycloak token",
            headers={"WWW-Authenticate": "Bearer"},
        )

        # ── Decode and verify JWT via JWKS ──
        try:
            jwks_client = _get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            expected_issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"

            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=expected_issuer,
                options={
                    "verify_exp": True,
                    "verify_aud": False,
                    "verify_iss": True,
                },
            )
            if not _token_matches_client(payload):
                raise InvalidAudienceError("Invalid audience / authorized party")
        except pyjwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except (InvalidTokenError, PyJWKClientError) as e:
            logger.warning("keycloak.token_validation_failed", error=str(e))
            raise credentials_exception from e

        # ── Extract claims ──
        keycloak_sub: str | None = payload.get("sub")
        email: str | None = payload.get("email")
        given_name: str = payload.get("given_name", "")
        family_name: str = payload.get("family_name", "")
        preferred_username: str = payload.get("preferred_username", "")

        if not keycloak_sub or not email:
            logger.warning("keycloak.missing_claims", sub=keycloak_sub, email=email)
            raise credentials_exception

        name = f"{given_name} {family_name}".strip() or preferred_username

        # ── Extract roles from token ──
        roles = payload.get("roles", [])
        realm_access = payload.get("realm_access", {})
        realm_roles = realm_access.get("roles", [])
        all_roles = set(roles) | set(realm_roles)

        # Map Keycloak roles to TW roles
        if "tw_admin" in all_roles:
            role = "admin"
        elif "tw_viewer" in all_roles:
            role = "viewer"
        else:
            role = "editor"

        # ── Find or auto-provision user ──
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            # Auto-provision: create TW user for this Keycloak identity
            user = User(
                email=email,
                name=name,
                hashed_password="__keycloak_managed__",  # No local password
                role=role,
                is_verified=True,  # Keycloak handles verification
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(
                "keycloak.user_auto_provisioned",
                user_id=user.id,
                email=email,
                keycloak_sub=keycloak_sub,
            )
        else:
            # Update role and name from Keycloak if changed
            changed = False
            if user.name != name:
                user.name = name
                changed = True
            if user.role != role:
                user.role = role
                changed = True
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account disabled",
                )
            if not user.is_verified:
                # Legacy user not yet verified — Keycloak login implicitly verifies
                user.is_verified = True
                changed = True
                logger.info(
                    "keycloak.audit.legacy_user_verified",
                    user_id=user.id,
                    email=email,
                    keycloak_sub=keycloak_sub,
                )
            if changed:
                await db.commit()
                logger.info(
                    "keycloak.audit.user_synced",
                    user_id=user.id,
                    email=email,
                    keycloak_sub=keycloak_sub,
                    role=role,
                )

        # ── Audit: successful authentication ──
        logger.info(
            "keycloak.audit.login_success",
            user_id=user.id,
            email=email,
            keycloak_sub=keycloak_sub,
            role=role,
            is_new_user=(
                user.hashed_password == "__keycloak_managed__"
                and not any(r in all_roles for r in ("tw_admin",))
            ),
        )

        return AuthenticatedUser.model_validate(user).model_copy(update={"auth_source": "keycloak"})
