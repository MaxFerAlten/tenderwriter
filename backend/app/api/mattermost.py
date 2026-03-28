"""TenderWriter — Mattermost Full Chat API.

Provides the endpoint for opening a "Full Chat" session in Mattermost,
automatically creating the user, channel, and session token.

Supports two modes:
- legacy: creates PAT for cookie-based auto-login
- keycloak: provisions channel/membership only, relies on SSO for auth
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models import Tender
from app.api.auth import get_current_user, UserResponse
from app.services.mattermost import create_fullchat_session, create_sso_chat_session, is_mm_oidc_ready

import structlog

logger = structlog.get_logger()

router = APIRouter()


class FullChatResponse(BaseModel):
    mm_url: str
    mm_token: str           # Empty string when SSO mode (no browser session needed)
    channel_name: str
    mm_user_id: str
    mm_username: str
    auth_mode: str = "legacy"  # "legacy" or "sso" — tells frontend how to handle


@router.post("/{tender_id}/fullchat", response_model=FullChatResponse)
async def open_fullchat(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Mattermost Full Chat session for the given tender.

    - Ensures the current user has a Mattermost account
    - Ensures a private channel exists for this tender
    - Adds the user to the channel
    - In legacy mode: returns URL + browser session for cookie auto-login
    - In keycloak mode: returns URL only (SSO handles auth via redirect)
    """
    # Verify tender exists
    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    use_sso = (
        (settings.auth_provider or "").strip().lower() == "keycloak"
        and await is_mm_oidc_ready()
    )

    try:
        if use_sso:
            session = await create_sso_chat_session(
                tender_id=tender.id,
                tender_title=tender.title,
                user_email=current_user.email,
                user_name=current_user.name,
                tw_user_id=current_user.id,
            )
        else:
            if (settings.auth_provider or "").strip().lower() == "keycloak":
                logger.warning(
                    "mattermost.fullchat_fallback_legacy",
                    tender_id=tender_id,
                    reason="mattermost_oidc_not_ready",
                )
            session = await create_fullchat_session(
                tender_id=tender.id,
                tender_title=tender.title,
                user_email=current_user.email,
                user_name=current_user.name,
                tw_user_id=current_user.id,
            )
    except Exception as exc:
        logger.error("mattermost.fullchat_failed", error=str(exc), tender_id=tender_id)
        raise HTTPException(status_code=502, detail=f"Mattermost integration error: {exc}")

    return FullChatResponse(
        mm_url=session.mm_url,
        mm_token=session.mm_token,
        channel_name=session.channel_name,
        mm_user_id=session.mm_user_id,
        mm_username=session.mm_username,
        auth_mode="sso" if use_sso else "legacy",
    )
