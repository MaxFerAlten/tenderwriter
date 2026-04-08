"""Minimal provider client wrapper (Wave 1)."""

from __future__ import annotations

class ProviderClient:
    def __init__(self, provider: str):
        self.provider = provider

    def fetch(self, *args, **kwargs):
        # Placeholder for real provider fetch logic
        return {"provider": self.provider, "data": None}
