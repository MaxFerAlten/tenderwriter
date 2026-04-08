"""Model Fallback Orchestration.

Ported from OpenClaw's model-fallback.ts.
Implements the outer retry loop that cycles through model candidates.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, TypeVar, Union

from backend.services.advanced_fallback.auth_profiles import (
    AuthProfileStoreManager,
    get_auth_profile_manager,
)
from backend.services.advanced_fallback.cooldown import (
    PROBE_MARGIN_MS,
    CooldownDecision,
    resolve_cooldown_decision,
)
from backend.services.advanced_fallback.errors import (
    FailoverError,
    FailoverReason,
    FailoverSummaryError,
    coerce_to_failover_error,
    is_context_overflow_error,
)
from backend.services.advanced_fallback.policy import (
    FallbackDecision,
    FallbackDecisionAction,
    FallbackPolicy,
    Stage,
    resolve_fallback_decision,
)

logger = logging.getLogger("tenderclaw.advanced_fallback")

T = TypeVar("T")


@dataclass
class FallbackCandidate:
    """A candidate model/provider for fallback."""

    provider: str
    model: str
    is_primary: bool = True
    reason: Optional[str] = None  # Why this candidate was selected


@dataclass
class FallbackAttempt:
    """Record of a single fallback attempt."""

    provider: str
    model: str
    profile_id: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[FailoverReason] = None
    status: Optional[int] = None
    duration_ms: float = 0
    success: bool = False


@dataclass
class ModelFallbackResult:
    """Result of a successful fallback run."""

    result: Any
    provider: str
    model: str
    profile_id: Optional[str] = None
    attempts: List[FallbackAttempt] = field(default_factory=list)


@dataclass
class ModelFallbackConfig:
    """Configuration for the fallback system."""

    enabled: bool = True
    fallback_models: List[str] = field(default_factory=list)
    max_retries_per_model: int = 2
    max_total_attempts: int = 10
    use_auth_profiles: bool = True
    probe_enabled: bool = True

    @classmethod
    def from_config(cls, config: Optional[dict] = None) -> ModelFallbackConfig:
        """Create config from TenderClawConfig.

        Expects config structure:
        {
            "experimental": {
                "advancedFallback": {
                    "enabled": true,
                    "fallbackModels": [...],
                    ...
                }
            }
        }
        """
        if not config:
            return cls()
        exp = config.get("experimental", {})
        af = exp.get("advancedFallback", {}) if isinstance(exp, dict) else {}
        return cls(
            enabled=af.get("enabled", False),
            fallback_models=af.get("fallbackModels", []),
            max_retries_per_model=af.get("maxRetriesPerModel", 2),
            max_total_attempts=af.get("maxTotalAttempts", 10),
            use_auth_profiles=af.get("useAuthProfiles", True),
            probe_enabled=af.get("probeEnabled", True),
        )


async def run_with_model_fallback(
    provider: str,
    model: str,
    run: Callable[[str, str, Optional[str]], Union[T, asyncio.coroutine]],
    config: Optional[ModelFallbackConfig] = None,
    fallback_override: Optional[List[str]] = None,
    auth_manager: Optional[AuthProfileStoreManager] = None,
    policy: Optional[FallbackPolicy] = None,
    on_error: Optional[Callable[[FailoverError], None]] = None,
) -> ModelFallbackResult:
    """Run with automatic model and profile fallback.

    This is the main entry point for the advanced fallback system.
    It implements the outer retry loop that:
    1. Tries the primary model with profile rotation
    2. Falls back to alternative models if configured
    3. Handles cooldowns and probes

    Args:
        provider: Primary provider (e.g., "anthropic")
        model: Primary model (e.g., "claude-opus-4-20250514")
        run: Async function to execute. Signature: (provider, model, profile_id) -> T
        config: Fallback configuration
        fallback_override: Explicit fallback chain (e.g., ["openai/gpt-5", "google/gemini"])
        auth_manager: Auth profile manager (uses global if not provided)
        policy: Fallback policy
        on_error: Callback for errors (for logging, etc.)

    Returns:
        ModelFallbackResult with successful result and attempt history

    Raises:
        FailoverSummaryError: All candidates exhausted
    """
    config = config or ModelFallbackConfig()
    policy = policy or FallbackPolicy()
    auth_manager = auth_manager or get_auth_profile_manager()

    if not config.enabled:
        # Fallback disabled - just run directly
        result = await _ensure_coro(run(provider, model, None))
        return ModelFallbackResult(
            result=result,
            provider=provider,
            model=model,
        )

    # Build candidate list
    candidates = _resolve_candidates(provider, model, config, fallback_override)

    attempts: List[FallbackAttempt] = []
    total_attempts = 0

    for candidate in candidates:
        # Clear expired cooldowns before each candidate
        auth_manager.clear_expired_cooldowns()

        # Get ordered profiles for this provider
        if config.use_auth_profiles:
            profiles = auth_manager.get_ordered_profiles(candidate.provider)
        else:
            profiles = []

        # If no profiles, just try once
        if not profiles:
            profiles = [None]  # Single attempt with no profile rotation

        candidate_attempts = 0
        profile_rotated = False

        for profile in profiles:
            if total_attempts >= config.max_total_attempts:
                break

            profile_id = profile.profile_id if profile else None

            # Check cooldown decision
            if profile and not profile.is_usable:
                decision = resolve_cooldown_decision(
                    reason=profile.stats.cooldown_reason or FailoverReason.UNKNOWN,
                    is_primary=candidate.is_primary,
                    has_fallback_candidates=len(candidates) > 1,
                    cooldown_expiry=profile.stats.cooldown_until,
                    requested_now=False,
                    last_probe_at=profile.stats.probe_last_attempt,
                )

                if decision.type == "skip":
                    logger.debug(
                        f"Skipping profile {profile_id} - cooldown: {decision.reason}"
                    )
                    continue
                elif decision.type == "probe":
                    # Mark that we're probing
                    profile.stats.probe_last_attempt = time.time()

            # Attempt the request
            start_time = time.time()
            try:
                result = await _ensure_coro(run(candidate.provider, candidate.model, profile_id))
                duration_ms = (time.time() - start_time) * 1000

                # Success!
                if profile_id:
                    auth_manager.mark_profile_success(profile_id)

                attempts.append(FallbackAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    profile_id=profile_id,
                    duration_ms=duration_ms,
                    success=True,
                ))

                return ModelFallbackResult(
                    result=result,
                    provider=candidate.provider,
                    model=candidate.model,
                    profile_id=profile_id,
                    attempts=attempts,
                )

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                failover_error = coerce_to_failover_error(
                    e, candidate.provider, candidate.model, profile_id
                )

                # Log error callback
                if on_error:
                    try:
                        on_error(failover_error)
                    except Exception:
                        pass

                # Context overflow = never fallback
                if is_context_overflow_error(failover_error):
                    raise FailoverSummaryError(
                        attempts=attempts,
                        soonest_cooldown_expiry=None,
                        total_candidates=len(candidates),
                    )

                # Record failure
                attempts.append(FallbackAttempt(
                    provider=candidate.provider,
                    model=candidate.model,
                    profile_id=profile_id,
                    error=str(e),
                    reason=failover_error.reason,
                    status=failover_error.status,
                    duration_ms=duration_ms,
                    success=False,
                ))

                # Apply cooldown to profile
                if profile_id:
                    cooldown_ms = _get_cooldown_ms(failover_error.reason)
                    auth_manager.mark_profile_failure(
                        profile_id,
                        failover_error.reason,
                        model=candidate.model,
                        cooldown_ms=cooldown_ms,
                    )

                # Decide what to do next
                decision = resolve_fallback_decision(
                    stage=Stage.PROMPT,
                    reason=failover_error.reason,
                    profile_rotated=profile_rotated,
                    fallback_configured=len(candidates) > 1,
                    retry_count=candidate_attempts,
                    max_retries=config.max_retries_per_model,
                    policy=policy,
                )

                if decision.action == FallbackDecisionAction.ROTATE_PROFILE:
                    profile_rotated = True
                    continue

                elif decision.action == FallbackDecisionAction.FALLBACK_MODEL:
                    break  # Move to next candidate

                elif decision.action == FallbackDecisionAction.SURFACE_ERROR:
                    raise FailoverError(
                        reason=failover_error.reason,
                        provider=candidate.provider,
                        model=candidate.model,
                        status=failover_error.status,
                        message=str(e),
                    )

                elif decision.action == FallbackDecisionAction.RETURN_ERROR_PAYLOAD:
                    raise FailoverSummaryError(
                        attempts=attempts,
                        soonest_cooldown_expiry=_get_soonest_cooldown(auth_manager),
                        total_candidates=len(candidates),
                    )

            total_attempts += 1
            candidate_attempts += 1

    # All candidates exhausted
    raise FailoverSummaryError(
        attempts=attempts,
        soonest_cooldown_expiry=_get_soonest_cooldown(auth_manager),
        total_candidates=len(candidates),
    )


def _resolve_candidates(
    provider: str,
    model: str,
    config: ModelFallbackConfig,
    fallback_override: Optional[List[str]] = None,
) -> List[FallbackCandidate]:
    """Build the list of fallback candidates."""
    candidates = [FallbackCandidate(provider=provider, model=model, is_primary=True)]

    # Use explicit override if provided
    if fallback_override:
        for fb in fallback_override:
            fb_provider, fb_model = _parse_model_string(fb)
            candidates.append(FallbackCandidate(
                provider=fb_provider,
                model=fb_model,
                is_primary=False,
                reason="explicit_override",
            ))
        return candidates

    # Use configured fallbacks
    for fb in config.fallback_models:
        fb_provider, fb_model = _parse_model_string(fb)
        candidates.append(FallbackCandidate(
            provider=fb_provider,
            model=fb_model,
            is_primary=False,
            reason="configured_fallback",
        ))

    return candidates


def _parse_model_string(model_str: str) -> tuple[str, str]:
    """Parse provider/model string.

    Examples:
        "anthropic/claude-opus-4" -> ("anthropic", "claude-opus-4")
        "claude-opus-4" -> ("anthropic", "claude-opus-4")
    """
    if "/" in model_str:
        parts = model_str.split("/", 1)
        return parts[0], parts[1]
    return "anthropic", model_str


def _get_cooldown_ms(reason: FailoverReason) -> Optional[int]:
    """Get cooldown duration based on reason."""
    if reason == FailoverReason.RATE_LIMIT:
        return 30_000  # 30 seconds
    elif reason == FailoverReason.OVERLOADED:
        return 60_000  # 1 minute
    elif reason == FailoverReason.TIMEOUT:
        return 30_000  # 30 seconds
    elif reason == FailoverReason.BILLING:
        return 5 * 60 * 60 * 1000  # 5 hours
    elif reason == FailoverReason.AUTH:
        return 5 * 60 * 1000  # 5 minutes
    elif reason == FailoverReason.AUTH_PERMANENT:
        return 10 * 60 * 1000  # 10 minutes
    return None


def _get_soonest_cooldown(auth_manager: AuthProfileStoreManager) -> Optional[float]:
    """Get the soonest cooldown expiry across all profiles."""
    now = time.time()
    soonest = None

    for profile in auth_manager.list_all_profiles():
        unusable = profile.stats.unusable_until(now)
        if unusable > now:
            if soonest is None or unusable < soonest:
                soonest = unusable

    return soonest


def _ensure_coro(obj: Union[T, Any]) -> Any:
    """Ensure result is a coroutine, await if needed."""
    if asyncio.iscoroutine(obj):
        return obj
    return obj
