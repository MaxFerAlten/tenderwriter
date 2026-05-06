"""
TenderWriter — Auth Provider Abstraction

Pluggable authentication layer. The active provider is selected via
the AUTH_PROVIDER environment variable (default: "legacy").

Usage in any router:
    from app.auth import get_current_user, UserResponse
"""

from app.auth.provider import UserResponse, get_current_user  # noqa: F401
