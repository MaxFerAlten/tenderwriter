"""Advanced Model Fallback System.

Opt-in alternative to TenderClaw's basic model router.
Implements OpenClaw-style multi-key rotation, cooldown tracking,
and intelligent model fallback chains.

Enable via TenderClawConfig:
    experimental:
        advanced_fallback: true
        auth_profiles: true
"""

from backend.services.advanced_fallback.errors import (
    FailoverError,
    FailoverReason,
    FailoverSummaryError,
    classify_provider_error,
    coerce_to_failover_error,
)
from backend.services.advanced_fallback.auth_profiles import (
    AuthProfile,
    AuthProfileCredential,
    AuthProfileStore,
    AuthProfileStoreManager,
    auth_profile_manager,
    get_auth_profile_manager,
)
from backend.services.advanced_fallback.cooldown import (
    CooldownDecision,
    TwoLaneCooldown,
    clear_expired_cooldowns,
    calculate_transient_cooldown,
    calculate_persistent_cooldown,
    resolve_cooldown_decision,
)
from backend.services.advanced_fallback.fallback import (
    FallbackCandidate,
    ModelFallbackConfig,
    ModelFallbackResult,
    run_with_model_fallback,
)
from backend.services.advanced_fallback.policy import (
    FallbackDecision,
    FallbackPolicy,
    resolve_fallback_decision,
)

__all__ = [
    "FailoverError",
    "FailoverReason",
    "FailoverSummaryError",
    "classify_provider_error",
    "coerce_to_failover_error",
    "AuthProfile",
    "AuthProfileCredential",
    "AuthProfileStore",
    "AuthProfileStoreManager",
    "auth_profile_manager",
    "get_auth_profile_manager",
    "CooldownDecision",
    "TwoLaneCooldown",
    "clear_expired_cooldowns",
    "calculate_transient_cooldown",
    "calculate_persistent_cooldown",
    "resolve_cooldown_decision",
    "FallbackCandidate",
    "ModelFallbackConfig",
    "ModelFallbackResult",
    "run_with_model_fallback",
    "FallbackDecision",
    "FallbackPolicy",
    "resolve_fallback_decision",
]
