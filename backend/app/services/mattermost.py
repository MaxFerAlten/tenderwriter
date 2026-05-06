"""Mattermost integration service — user sync, channel-per-tender, browser sessions.

Talks to the Mattermost REST API v4 using an admin bot token to:
1. Ensure a Mattermost user exists for each TenderWriter user
2. Create/find a channel per tender
3. Add users to the tender channel
4. Generate a browser session token for auto-login
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration — read from env (same .env used by docker-compose)
# ---------------------------------------------------------------------------

MM_INTERNAL_URL = os.environ.get("MM_INTERNAL_URL", "http://mattermost:8065")
MM_SUBPATH = os.environ.get("MM_SUBPATH", "/mm")
MM_EDITION = os.environ.get("MM_EDITION", "enterprise")  # "enterprise" or "team"
MM_ADMIN_TOKEN: str | None = None  # lazy-initialized


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a Mattermost-safe channel name (lowercase, hyphens, max 64 chars)."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] if slug else "channel"


async def _get_admin_token() -> str:
    """Get or create a Mattermost admin personal access token.

    On first call, logs in as tw-admin and creates a PAT for API use.
    Caches the token for subsequent calls.
    """
    global MM_ADMIN_TOKEN
    if MM_ADMIN_TOKEN:
        return MM_ADMIN_TOKEN

    admin_user = os.environ.get("MM_ADMIN_USER", "tw-admin")
    admin_pass = os.environ.get("MM_ADMIN_PASS", "TW2026Secure!Pass")

    async with httpx.AsyncClient(base_url=MM_INTERNAL_URL, timeout=15) as client:
        # Login
        resp = await client.post(
            f"{MM_SUBPATH}/api/v4/users/login",
            json={
                "login_id": admin_user,
                "password": admin_pass,
            },
        )
        resp.raise_for_status()
        session_token = resp.headers["token"]

        # Get user ID
        me = resp.json()
        user_id = me["id"]

        # Create a personal access token
        resp2 = await client.post(
            f"{MM_SUBPATH}/api/v4/users/{user_id}/tokens",
            json={"description": "TenderWriter backend integration"},
            headers={"Authorization": f"Bearer {session_token}"},
        )
        resp2.raise_for_status()
        MM_ADMIN_TOKEN = resp2.json()["token"]

    logger.info("mattermost.admin_token_created")
    return MM_ADMIN_TOKEN


async def _api(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an authenticated request to the Mattermost API."""
    token = await _get_admin_token()
    async with httpx.AsyncClient(base_url=MM_INTERNAL_URL, timeout=15) as client:
        resp = await client.request(
            method,
            f"{MM_SUBPATH}{path}",
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )
        return resp


async def is_mm_oidc_ready() -> bool:
    """Return whether Mattermost currently exposes OpenID login to clients.

    We inspect the same public client config payload the web UI uses. When this
    flag is false, redirecting a browser to Mattermost won't produce an SSO
    hand-off and we should gracefully fall back to the legacy PAT flow.
    """
    try:
        async with httpx.AsyncClient(base_url=MM_INTERNAL_URL, timeout=10) as client:
            resp = await client.get(f"{MM_SUBPATH}/api/v4/config/client?format=old")
            resp.raise_for_status()
            config = resp.json()
    except Exception as exc:
        logger.warning("mattermost.oidc_probe_failed", error=str(exc))
        return False

    return str(config.get("EnableSignUpWithOpenId", "")).strip().lower() == "true"


async def is_mm_plugin_oidc_ready() -> bool:
    """Return whether the TW OIDC plugin is active on Mattermost Team Edition.

    Queries the plugin's /health endpoint. When it responds with
    {"enabled": true, "initialized": true}, the plugin is ready.
    """
    try:
        async with httpx.AsyncClient(base_url=MM_INTERNAL_URL, timeout=5) as client:
            resp = await client.get(f"{MM_SUBPATH}/plugins/com.tenderwriter.oidc/health")
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("enabled") is True and data.get("initialized") is True
    except Exception as exc:
        logger.debug("mattermost.plugin_oidc_probe_failed", error=str(exc))
        return False


async def get_mm_sso_mode() -> str:
    """Determine which SSO mode to use for Mattermost.

    Returns:
        "native_oidc"  — Enterprise Edition with native OpenID Connect
        "plugin_oidc"  — Team Edition with TW OIDC plugin
        "legacy"       — No SSO, use PAT-based browser sessions
    """
    from app.config import settings

    auth_provider = (settings.auth_provider or "").strip().lower()

    if auth_provider != "keycloak":
        return "legacy"

    if MM_EDITION == "enterprise" and await is_mm_oidc_ready():
        return "native_oidc"

    if MM_EDITION == "team" and await is_mm_plugin_oidc_ready():
        return "plugin_oidc"

    return "legacy"


async def get_mm_sso_mode_for_auth_source(auth_source: str | None) -> str:
    """Determine the Mattermost SSO mode for the current TenderWriter session.

    In hybrid auth mode, only Keycloak-backed TenderWriter sessions should use
    Mattermost SSO. Legacy TenderWriter sessions must keep using the fallback
    browser-session flow so that both login methods can coexist.
    """
    from app.config import settings

    auth_provider = (settings.auth_provider or "").strip().lower()
    normalized_source = (auth_source or "").strip().lower()

    if auth_provider == "legacy":
        return "legacy"

    if auth_provider == "keycloak":
        normalized_source = "keycloak"

    if normalized_source != "keycloak":
        return "legacy"

    if MM_EDITION == "enterprise" and await is_mm_oidc_ready():
        return "native_oidc"

    if MM_EDITION == "team" and await is_mm_plugin_oidc_ready():
        return "plugin_oidc"

    return "legacy"


# ---------------------------------------------------------------------------
# Team helpers
# ---------------------------------------------------------------------------

_TEAM_ID_CACHE: str | None = None


async def _get_team_id() -> str:
    """Get the TenderWriter team ID (assumes a single team)."""
    global _TEAM_ID_CACHE
    if _TEAM_ID_CACHE:
        return _TEAM_ID_CACHE

    resp = await _api("GET", "/api/v4/teams")
    resp.raise_for_status()
    teams = resp.json()
    if not teams:
        raise RuntimeError("No Mattermost teams found")
    _TEAM_ID_CACHE = teams[0]["id"]
    return _TEAM_ID_CACHE


# ---------------------------------------------------------------------------
# User sync
# ---------------------------------------------------------------------------


async def ensure_mm_user(email: str, name: str, tw_user_id: int) -> tuple[str, str]:
    """Ensure a Mattermost user exists for the given TW user. Returns (MM user ID, username)."""
    # Try to find by email
    resp = await _api("GET", f"/api/v4/users/email/{email}")
    if resp.status_code == 200:
        mm_user = resp.json()
        # Ensure user is in the team (ignore "already member" errors)
        team_id = await _get_team_id()
        team_resp = await _api(
            "POST",
            f"/api/v4/teams/{team_id}/members",
            json={
                "team_id": team_id,
                "user_id": mm_user["id"],
            },
        )
        if team_resp.status_code not in (200, 201):
            # Log but don't fail — user may already be a member
            logger.debug(
                "mattermost.team_membership_response",
                status=team_resp.status_code,
                mm_user_id=mm_user["id"],
            )
        return mm_user["id"], mm_user["username"]

    # Create the user
    username = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())
    # Ensure unique
    username = f"{username}-tw{tw_user_id}"

    resp = await _api(
        "POST",
        "/api/v4/users",
        json={
            "email": email,
            "username": username,
            "password": f"TW!{secrets.token_urlsafe(32)}",
            "first_name": name.split()[0] if name else "",
            "last_name": " ".join(name.split()[1:]) if name and " " in name else "",
        },
    )
    resp.raise_for_status()
    mm_user = resp.json()

    # Add to team
    team_id = await _get_team_id()
    await _api(
        "POST",
        f"/api/v4/teams/{team_id}/members",
        json={
            "team_id": team_id,
            "user_id": mm_user["id"],
        },
    )

    logger.info("mattermost.user_created", email=email, mm_user_id=mm_user["id"])
    return mm_user["id"], mm_user["username"]


# ---------------------------------------------------------------------------
# Best-effort provisioning (called from auth hooks)
# ---------------------------------------------------------------------------


async def provision_mm_user_for_tw_user(
    *,
    user_email: str,
    user_name: str,
    tw_user_id: int,
) -> None:
    """Best-effort Mattermost user provisioning after successful TW auth.

    - Ensures the Mattermost account exists
    - Ensures the user belongs to the default team
    - Never raises to the caller
    """
    if not user_email:
        return

    try:
        mm_user_id, mm_username = await ensure_mm_user(
            email=user_email,
            name=user_name,
            tw_user_id=tw_user_id,
        )
        logger.info(
            "mattermost.user_provisioned_on_auth",
            tw_user_id=tw_user_id,
            mm_user_id=mm_user_id,
            mm_username=mm_username,
        )
    except Exception as exc:
        logger.warning(
            "mattermost.user_provisioning_failed",
            tw_user_id=tw_user_id,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Channel per tender
# ---------------------------------------------------------------------------


async def ensure_tender_channel(tender_id: int, tender_title: str) -> str:
    """Ensure a Mattermost channel exists for the given tender. Returns channel ID."""
    team_id = await _get_team_id()
    channel_name = f"tender-{tender_id}-{_slugify(tender_title, 40)}"

    # Try to find existing channel
    resp = await _api("GET", f"/api/v4/teams/{team_id}/channels/name/{channel_name}")
    if resp.status_code == 200:
        return resp.json()["id"]

    # Create channel
    resp = await _api(
        "POST",
        "/api/v4/channels",
        json={
            "team_id": team_id,
            "name": channel_name,
            "display_name": f"Tender: {tender_title[:50]}",
            "type": "P",  # Private channel — only assigned users
            "purpose": f"Chat & video call per tender #{tender_id}",
        },
    )
    resp.raise_for_status()
    channel = resp.json()
    logger.info("mattermost.channel_created", tender_id=tender_id, channel_id=channel["id"])
    return channel["id"]


# ---------------------------------------------------------------------------
# Add user to channel
# ---------------------------------------------------------------------------


async def add_user_to_channel(channel_id: str, mm_user_id: str) -> None:
    """Add a Mattermost user to a channel (idempotent)."""
    resp = await _api(
        "POST",
        f"/api/v4/channels/{channel_id}/members",
        json={
            "user_id": mm_user_id,
        },
    )
    # 201 = added, already member returns 200 or similar
    if resp.status_code not in (200, 201):
        logger.warning("mattermost.add_member_failed", status=resp.status_code, body=resp.text)


# ---------------------------------------------------------------------------
# Browser session for Full Chat fallback
# ---------------------------------------------------------------------------


async def create_user_browser_session(
    *,
    mm_user_id: str,
    login_id: str,
) -> str:
    """Mint a real Mattermost browser session for legacy Full Chat fallback.

    User access tokens are valid for API authentication, but current Mattermost
    web login expects a regular session token stored in the `MMAUTHTOKEN`
    cookie. We rotate the local Mattermost password to a one-time random value,
    log the user in through the standard login endpoint, and return the session
    token from the response headers.
    """
    temp_password = f"TW!{secrets.token_urlsafe(24)}"

    reset_resp = await _api(
        "PUT",
        f"/api/v4/users/{mm_user_id}/password",
        json={"new_password": temp_password},
    )
    reset_resp.raise_for_status()

    async with httpx.AsyncClient(base_url=MM_INTERNAL_URL, timeout=15) as client:
        login_resp = await client.post(
            f"{MM_SUBPATH}/api/v4/users/login",
            json={
                "login_id": login_id,
                "password": temp_password,
            },
        )
        login_resp.raise_for_status()

    session_token = login_resp.headers.get("Token")
    if not session_token:
        raise RuntimeError("Mattermost login did not return a session token")

    logger.info("mattermost.browser_session_created", mm_user_id=mm_user_id)
    return session_token


# ---------------------------------------------------------------------------
# High-level: Full Chat session
# ---------------------------------------------------------------------------


@dataclass
class FullChatSession:
    mm_url: str  # Deep-link to the channel on MM public URL
    mm_token: str  # Browser session token for auto-login (empty in SSO mode)
    channel_name: str  # Channel name for display
    mm_user_id: str  # MM user ID
    mm_username: str  # MM username for display/login


async def create_fullchat_session(
    tender_id: int,
    tender_title: str,
    user_email: str,
    user_name: str,
    tw_user_id: int,
) -> FullChatSession:
    """Create everything needed for a user to open Full Chat for a tender.

    1. Ensure MM user exists
    2. Ensure tender channel exists
    3. Add user to channel
    4. Create browser session token
    5. Return deep-link URL + token
    """
    mm_user_id, mm_username = await ensure_mm_user(user_email, user_name, tw_user_id)
    channel_id = await ensure_tender_channel(tender_id, tender_title)
    await add_user_to_channel(channel_id, mm_user_id)
    token = await create_user_browser_session(mm_user_id=mm_user_id, login_id=user_email)

    team_id = await _get_team_id()
    # Get team name for URL
    resp = await _api("GET", f"/api/v4/teams/{team_id}")
    resp.raise_for_status()
    team_name = resp.json()["name"]

    channel_name = f"tender-{tender_id}-{_slugify(tender_title, 40)}"
    # Return relative /mm/ path so the browser uses the same-origin Nginx proxy
    mm_url = f"/mm/{team_name}/channels/{channel_name}"

    return FullChatSession(
        mm_url=mm_url,
        mm_token=token,
        channel_name=channel_name,
        mm_user_id=mm_user_id,
        mm_username=mm_username,
    )


async def create_sso_chat_session(
    tender_id: int,
    tender_title: str,
    user_email: str,
    user_name: str,
    tw_user_id: int,
    sso_mode: str = "native_oidc",
) -> FullChatSession:
    """Create everything needed for SSO-based Full Chat (no PAT generated).

    When Keycloak SSO is active, the browser already has a valid Keycloak session.
    Mattermost will authenticate the user via OIDC redirect — no token/cookie needed.

    Steps:
    1. Ensure MM user exists
    2. Ensure tender channel exists
    3. Add user to channel
    4. Return deep-link URL (no token)
    """
    if sso_mode not in {"native_oidc", "plugin_oidc"}:
        raise ValueError(f"Unsupported Mattermost SSO mode: {sso_mode}")

    mm_user_id, mm_username = await ensure_mm_user(user_email, user_name, tw_user_id)
    channel_id = await ensure_tender_channel(tender_id, tender_title)
    await add_user_to_channel(channel_id, mm_user_id)

    team_id = await _get_team_id()
    resp = await _api("GET", f"/api/v4/teams/{team_id}")
    resp.raise_for_status()
    team_name = resp.json()["name"]

    channel_name = f"tender-{tender_id}-{_slugify(tender_title, 40)}"
    channel_path = f"/mm/{team_name}/channels/{channel_name}"
    mm_url = channel_path

    if sso_mode == "plugin_oidc":
        mm_url = (
            f"/mm/plugins/com.tenderwriter.oidc/login?redirect_to={quote(channel_path, safe='')}"
        )

    return FullChatSession(
        mm_url=mm_url,
        mm_token="",  # No token needed — SSO handles auth
        channel_name=channel_name,
        mm_user_id=mm_user_id,
        mm_username=mm_username,
    )
