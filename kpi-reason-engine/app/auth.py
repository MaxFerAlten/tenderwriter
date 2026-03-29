"""Authentication helpers for internal tw-kpi-reason-engine routes."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

import app.config as app_config


def require_internal_service(request: Request) -> None:
    """Allow only trusted internal callers on protected service routes."""

    expected_token = (app_config.settings.service_token or "").strip()
    if not expected_token:
        return

    auth_header = request.headers.get("Authorization", "")
    service_token = request.headers.get("X-Service-Token", "").strip()

    bearer_token = ""
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()

    if bearer_token == expected_token or service_token == expected_token:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid service credentials.",
    )
