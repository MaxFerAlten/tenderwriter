"""
TenderWriter — Legacy JWT Auth Provider

Wraps the existing jose-based JWT validation as an AuthProvider.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.auth.base import AuthenticatedUser
from app.config import settings
from app.models import User

logger = structlog.get_logger()

ALGORITHM = "HS256"


class LegacyJWTProvider:
    """Auth provider using the original app-signed HS256 JWTs."""

    async def validate_token(
        self,
        token: str,
        db: AsyncSession,
    ) -> AuthenticatedUser:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        # ── Decode JWT ──
        try:
            payload = jwt.decode(
                token, settings.app_secret_key, algorithms=[ALGORITHM]
            )
            user_id: str | None = payload.get("sub")
            if user_id is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        # ── Fetch user from DB ──
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            raise credentials_exception
        result = await db.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception

        # ── Account guards (BUG-16 fix) ──
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled",
            )

        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account not verified",
            )

        return AuthenticatedUser.model_validate(user)
