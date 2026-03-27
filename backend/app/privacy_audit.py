from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse
from app.models import AnonymizerAuditLog


def mask_session_token(session_id: str | None) -> str | None:
    if not session_id:
        return None
    return f"{session_id[:8]}..."


async def persist_privacy_audit(
    *,
    db: AsyncSession | Any,
    action: str,
    current_user: UserResponse | None = None,
    tender_id: int | None = None,
    route_key: str | None = None,
    llm_route: str | None = None,
    anonymized: bool | None = None,
    target_id: int | None = None,
    target_provider: str | None = None,
    target_base_url: str | None = None,
    session_id: str | None = None,
    success: bool = True,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if not hasattr(db, "add") or not hasattr(db, "flush"):
        return
    db.add(
        AnonymizerAuditLog(
            action=action,
            user_id=None if current_user is None else current_user.id,
            user_email="" if current_user is None else current_user.email,
            user_role="" if current_user is None else current_user.role,
            tender_id=tender_id,
            route_key=route_key,
            llm_route=llm_route,
            anonymized=anonymized,
            target_id=target_id,
            target_provider=target_provider,
            target_base_url=target_base_url,
            session_token=mask_session_token(session_id),
            success=success,
            error_message=error_message,
            payload_json=dict(payload or {}),
        )
    )
    await db.flush()
