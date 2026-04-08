"""Auth Profiles System.

Ported from OpenClaw's auth-profiles/.
Manages multiple API keys per provider with intelligent rotation,
cooldowns, and health tracking.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

from backend.services.advanced_fallback.errors import FailoverReason

logger = logging.getLogger("tenderclaw.advanced_fallback.auth")

ProfileType = Literal["api_key", "oauth", "token"]


@dataclass
class ProfileUsageStats:
    """Usage statistics for a single auth profile."""

    last_used: Optional[float] = None
    cooldown_until: Optional[float] = None
    cooldown_reason: Optional[FailoverReason] = None
    cooldown_model: Optional[str] = None  # Model-scoped rate limit
    disabled_until: Optional[float] = None  # Persistent failure cooldown
    disabled_reason: Optional[str] = None
    error_count: int = 0
    failure_counts: Dict[str, int] = field(default_factory=dict)
    last_failure_at: Optional[float] = None
    probe_last_attempt: Optional[float] = None  # For cooldown probe throttling
    probe_success_at: Optional[float] = None

    def is_in_transient_cooldown(self, now: float) -> bool:
        """Check if profile is in transient cooldown (rate_limit, overloaded, etc)."""
        if self.cooldown_until is None:
            return False
        return now < self.cooldown_until

    def is_in_persistent_cooldown(self, now: float) -> bool:
        """Check if profile is permanently disabled (billing, auth_permanent)."""
        if self.disabled_until is None:
            return False
        return now < self.disabled_until

    def is_usable(self, now: float) -> bool:
        """Check if profile is usable (not in any cooldown)."""
        return not self.is_in_transient_cooldown(now) and not self.is_in_persistent_cooldown(now)

    def unusable_until(self, now: float) -> float:
        """Get the earliest time this profile becomes usable again."""
        times = []
        if self.cooldown_until and now < self.cooldown_until:
            times.append(self.cooldown_until)
        if self.disabled_until and now < self.disabled_until:
            times.append(self.disabled_until)
        return max(times) if times else now


@dataclass
class AuthProfileCredential:
    """Credential for an auth profile."""

    profile_id: str
    provider: str
    type: ProfileType = "api_key"
    api_key: str = ""
    api_key_ref: Optional[str] = None  # Reference to .env or secrets manager
    token: str = ""
    token_ref: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    expires_at: Optional[float] = None  # For OAuth tokens
    refresh_token: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """Check if OAuth/token credential is expired."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    def get_priority(self) -> int:
        """Get rotation priority. Lower = tried first.

        Priority: oauth (0) > token (1) > api_key (2)
        OAuth tokens can refresh automatically.
        """
        return {"oauth": 0, "token": 1, "api_key": 2}.get(self.type, 3)


@dataclass
class AuthProfile:
    """A single auth profile combining credential and usage stats."""

    credential: AuthProfileCredential
    stats: ProfileUsageStats = field(default_factory=ProfileUsageStats)
    order_hint: Optional[int] = None  # Explicit ordering hint

    @property
    def profile_id(self) -> str:
        return self.credential.profile_id

    @property
    def provider(self) -> str:
        return self.credential.provider

    @property
    def is_usable(self) -> bool:
        return self.stats.is_usable(time.time())

    def mark_used(self, now: float) -> None:
        """Mark profile as used successfully."""
        self.stats.last_used = now
        self.stats.error_count = 0
        self.stats.failure_counts = {}
        # Don't clear cooldowns on success - let them expire naturally


@dataclass
class AuthProfileStore:
    """Persistent storage for auth profiles and their stats."""

    version: int = 1
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    order: Dict[str, List[str]] = field(default_factory=dict)  # per-provider order
    last_good: Dict[str, str] = field(default_factory=dict)  # last successful per provider
    usage_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "version": self.version,
            "profiles": self.profiles,
            "order": self.order,
            "lastGood": self.last_good,
            "usageStats": self.usage_stats,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuthProfileStore:
        """Create from dict."""
        return cls(
            version=data.get("version", 1),
            profiles=data.get("profiles", {}),
            order=data.get("order", {}),
            last_good=data.get("lastGood", {}),
            usage_stats=data.get("usageStats", {}),
        )


class AuthProfileStoreManager:
    """Manages auth profile storage and lifecycle.

    Handles:
    - Loading/saving to disk
    - Profile CRUD operations
    - Ordering and rotation
    - Cooldown tracking
    """

    def __init__(self, store_path: Optional[Path] = None):
        self._store_path = store_path or Path.home() / ".tenderclaw" / "auth_profiles.json"
        self._store: AuthProfileStore = AuthProfileStore()
        self._dirty = False
        self._load()

    def _load(self) -> None:
        """Load profiles from disk."""
        if not self._store_path.exists():
            return

        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._store = AuthProfileStore.from_dict(data)
            logger.debug(f"Loaded {len(self._store.profiles)} auth profiles")
        except Exception as e:
            logger.warning(f"Failed to load auth profiles: {e}")

    def save(self) -> None:
        """Save profiles to disk."""
        if not self._dirty:
            return

        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(self._store.to_dict(), f, indent=2)
            self._dirty = False
            logger.debug("Saved auth profiles")
        except Exception as e:
            logger.error(f"Failed to save auth profiles: {e}")

    def add_profile(self, profile: AuthProfile) -> None:
        """Add or update an auth profile."""
        self._store.profiles[profile.profile_id] = {
            "provider": profile.credential.provider,
            "type": profile.credential.type,
            "apiKey": profile.credential.api_key,
            "apiKeyRef": profile.credential.api_key_ref,
            "token": profile.credential.token,
            "tokenRef": profile.credential.token_ref,
            "email": profile.credential.email,
            "displayName": profile.credential.display_name,
            "expiresAt": profile.credential.expires_at,
            "refreshToken": profile.credential.refresh_token,
        }
        self._store.usage_stats[profile.profile_id] = {
            "lastUsed": profile.stats.last_used,
            "cooldownUntil": profile.stats.cooldown_until,
            "cooldownReason": profile.stats.cooldown_reason.value if profile.stats.cooldown_reason else None,
            "cooldownModel": profile.stats.cooldown_model,
            "disabledUntil": profile.stats.disabled_until,
            "disabledReason": profile.stats.disabled_reason,
            "errorCount": profile.stats.error_count,
            "failureCounts": profile.stats.failure_counts,
            "lastFailureAt": profile.stats.last_failure_at,
        }
        self._dirty = True
        self.save()

    def remove_profile(self, profile_id: str) -> bool:
        """Remove an auth profile."""
        if profile_id not in self._store.profiles:
            return False

        del self._store.profiles[profile_id]
        self._store.usage_stats.pop(profile_id, None)

        # Remove from all order lists
        for provider_orders in self._store.order.values():
            if profile_id in provider_orders:
                provider_orders.remove(profile_id)

        # Remove from last_good
        self._store.last_good = {k: v for k, v in self._store.last_good.items() if v != profile_id}

        self._dirty = True
        self.save()
        return True

    def get_profile(self, profile_id: str) -> Optional[AuthProfile]:
        """Get a single profile by ID."""
        if profile_id not in self._store.profiles:
            return None

        data = self._store.profiles[profile_id]
        stats_data = self._store.usage_stats.get(profile_id, {})

        credential = AuthProfileCredential(
            profile_id=profile_id,
            provider=data.get("provider", ""),
            type=data.get("type", "api_key"),
            api_key=data.get("apiKey", ""),
            api_key_ref=data.get("apiKeyRef"),
            token=data.get("token", ""),
            token_ref=data.get("tokenRef"),
            email=data.get("email"),
            display_name=data.get("displayName"),
            expires_at=data.get("expiresAt"),
            refresh_token=data.get("refreshToken"),
        )

        stats = ProfileUsageStats(
            last_used=stats_data.get("lastUsed"),
            cooldown_until=stats_data.get("cooldownUntil"),
            cooldown_reason=FailoverReason(stats_data["cooldownReason"])
            if stats_data.get("cooldownReason")
            else None,
            cooldown_model=stats_data.get("cooldownModel"),
            disabled_until=stats_data.get("disabledUntil"),
            disabled_reason=stats_data.get("disabledReason"),
            error_count=stats_data.get("errorCount", 0),
            failure_counts=stats_data.get("failureCounts", {}),
            last_failure_at=stats_data.get("lastFailureAt"),
        )

        return AuthProfile(credential=credential, stats=stats)

    def get_profiles_for_provider(self, provider: str) -> List[AuthProfile]:
        """Get all profiles for a provider."""
        profiles = []
        for profile_id, data in self._store.profiles.items():
            if data.get("provider") == provider:
                profile = self.get_profile(profile_id)
                if profile:
                    profiles.append(profile)
        return profiles

    def get_ordered_profiles(
        self,
        provider: str,
        now: Optional[float] = None,
        explicit_order: Optional[List[str]] = None,
    ) -> List[AuthProfile]:
        """Get profiles for a provider in rotation order.

        Order by:
        1. Explicit order (if provided)
        2. Usable profiles first (not in cooldown)
        3. Within usable: by priority (oauth > token > api_key), then round-robin (oldest used first)
        4. Cooldown profiles last, sorted by expiry time
        """
        now = now or time.time()
        all_profiles = self.get_profiles_for_provider(provider)

        if not all_profiles:
            return []

        # Build base order
        if explicit_order:
            base_order = explicit_order
        elif provider in self._store.order:
            base_order = self._store.order[provider]
        else:
            base_order = [p.profile_id for p in all_profiles]

        # Separate usable and cooldown
        usable = [p for p in all_profiles if p.is_usable]
        in_cooldown = [p for p in all_profiles if not p.is_usable]

        # Sort usable: by priority, then round-robin (oldest used first)
        def sort_key(p: AuthProfile) -> tuple:
            return (p.credential.get_priority(), p.stats.last_used or 0)

        usable_sorted = sorted(usable, key=sort_key)

        # Sort cooldown by expiry time (soonest first)
        def cooldown_key(p: AuthProfile) -> float:
            return p.stats.unusable_until(now)

        cooldown_sorted = sorted(in_cooldown, key=cooldown_key)

        return usable_sorted + cooldown_sorted

    def mark_profile_failure(
        self,
        profile_id: str,
        reason: FailoverReason,
        now: Optional[float] = None,
        model: Optional[str] = None,
        cooldown_ms: Optional[int] = None,
    ) -> None:
        """Record a failure for a profile and apply cooldown."""
        now = now or time.time()
        profile = self.get_profile(profile_id)
        if not profile:
            return

        profile.stats.error_count += 1
        profile.stats.failure_counts[reason.value] = (
            profile.stats.failure_counts.get(reason.value, 0) + 1
        )
        profile.stats.last_failure_at = now

        # Apply cooldowns based on reason type
        if reason in (FailoverReason.RATE_LIMIT, FailoverReason.OVERLOADED, FailoverReason.TIMEOUT, FailoverReason.UNKNOWN):
            # Transient cooldown
            if cooldown_ms:
                profile.stats.cooldown_until = now + cooldown_ms / 1000
            profile.stats.cooldown_reason = reason
            profile.stats.cooldown_model = model
        elif reason in (FailoverReason.AUTH, FailoverReason.AUTH_PERMANENT, FailoverReason.BILLING):
            # Persistent cooldown
            if cooldown_ms:
                profile.stats.disabled_until = now + cooldown_ms / 1000
            profile.stats.disabled_reason = reason.value
            profile.stats.cooldown_until = None  # Clear transient
            profile.stats.cooldown_reason = None

        self.add_profile(profile)

    def mark_profile_success(self, profile_id: str, now: Optional[float] = None) -> None:
        """Record a successful request for a profile."""
        now = now or time.time()
        profile = self.get_profile(profile_id)
        if not profile:
            return

        profile.mark_used(now)
        self._store.last_good[profile.provider] = profile_id
        self.add_profile(profile)

    def clear_expired_cooldowns(self, now: Optional[float] = None) -> int:
        """Clear expired cooldowns. Returns number of profiles cleared."""
        now = now or time.time()
        cleared = 0

        for profile_id in list(self._store.usage_stats.keys()):
            profile = self.get_profile(profile_id)
            if not profile:
                continue

            changed = False

            # Clear expired transient cooldown
            if profile.stats.cooldown_until and now >= profile.stats.cooldown_until:
                profile.stats.cooldown_until = None
                profile.stats.cooldown_reason = None
                profile.stats.cooldown_model = None
                changed = True

            # Clear expired persistent cooldown
            if profile.stats.disabled_until and now >= profile.stats.disabled_until:
                profile.stats.disabled_until = None
                profile.stats.disabled_reason = None
                changed = True

            # Reset error counts when all cooldowns cleared (circuit breaker reset)
            if not profile.stats.unusable_until(now):
                if profile.stats.error_count > 0:
                    profile.stats.error_count = 0
                    profile.stats.failure_counts = {}
                    changed = True

            if changed:
                self.add_profile(profile)
                cleared += 1

        return cleared

    def list_all_profiles(self) -> List[AuthProfile]:
        """List all profiles."""
        return [p for p in (self.get_profile(pid) for pid in self._store.profiles) if p is not None]

    def get_stats_summary(self) -> Dict[str, Any]:
        """Get summary statistics for all profiles."""
        now = time.time()
        profiles = self.list_all_profiles()

        usable = sum(1 for p in profiles if p.is_usable)
        in_transient = sum(1 for p in profiles if p.stats.is_in_transient_cooldown(now))
        in_persistent = sum(1 for p in profiles if p.stats.is_in_persistent_cooldown(now))

        return {
            "total": len(profiles),
            "usable": usable,
            "in_transient_cooldown": in_transient,
            "in_persistent_cooldown": in_persistent,
            "providers": list(set(p.provider for p in profiles)),
        }


# Global singleton
_auth_profile_manager: Optional[AuthProfileStoreManager] = None


def get_auth_profile_manager() -> AuthProfileStoreManager:
    """Get the global auth profile manager instance."""
    global _auth_profile_manager
    if _auth_profile_manager is None:
        _auth_profile_manager = AuthProfileStoreManager()
    return _auth_profile_manager


auth_profile_manager = get_auth_profile_manager()
