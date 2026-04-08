"""OAuth placeholder for Wave 1."""

from __future__ import annotations

def get_oauth_token(provider: str, session_id: str) -> str:
    """Return a dummy OAuth token for given provider and session."""
    return f"token-{provider}-{session_id}"
