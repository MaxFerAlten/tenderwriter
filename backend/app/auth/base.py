"""
TenderWriter — Abstract Auth Provider

Defines the protocol that any auth provider must implement.
Adding a new provider (e.g., Keycloak OIDC) only requires:
  1. Implement AuthProvider
  2. Register it in provider.py
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class AuthenticatedUser(BaseModel):
    """Canonical user identity returned by any auth provider."""

    id: int
    email: str
    name: str
    role: str
    auth_source: str | None = None

    model_config = {"from_attributes": True}


@runtime_checkable
class AuthProvider(Protocol):
    """Contract that every authentication backend must satisfy."""

    async def validate_token(
        self,
        token: str,
        db: AsyncSession,
    ) -> AuthenticatedUser:
        """Validate a bearer token and return the authenticated user.

        Must raise ``fastapi.HTTPException`` on failure (401/403).
        """
        ...
