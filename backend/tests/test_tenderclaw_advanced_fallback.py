"""Tests for Advanced Model Fallback System.

Tests the OpenClaw-style model fallback, auth profiles, and cooldown system.
"""

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.services.advanced_fallback import (
    FailoverError,
    FailoverReason,
    FailoverSummaryError,
    ModelFallbackConfig,
    ModelFallbackResult,
    TwoLaneCooldown,
    classify_provider_error,
    coerce_to_failover_error,
    resolve_cooldown_decision,
    run_with_model_fallback,
)
from backend.services.advanced_fallback.auth_profiles import (
    AuthProfile,
    AuthProfileCredential,
    AuthProfileStore,
    AuthProfileStoreManager,
)
from backend.services.advanced_fallback.cooldown import (
    calculate_persistent_cooldown,
    calculate_transient_cooldown,
)
from backend.services.advanced_fallback.policy import (
    FallbackDecisionAction,
    FallbackPolicy,
    resolve_fallback_decision,
    Stage,
)


class TestFailoverErrorClassification:
    """Tests for error classification."""

    def test_classify_http_429_rate_limit(self):
        """Should classify 429 as rate_limit."""
        reason = classify_provider_error(status=429, message="Rate limit exceeded")
        assert reason == FailoverReason.RATE_LIMIT

    def test_classify_http_402_billing(self):
        """Should classify 402 as billing."""
        reason = classify_provider_error(status=402, message="Insufficient credits")
        assert reason == FailoverReason.BILLING

    def test_classify_http_401_auth(self):
        """Should classify 401 as auth."""
        reason = classify_provider_error(status=401, message="Invalid API key")
        assert reason == FailoverReason.AUTH

    def test_classify_http_403_auth_permanent(self):
        """Should classify 403 as auth_permanent."""
        reason = classify_provider_error(status=403, message="Forbidden")
        assert reason == FailoverReason.AUTH_PERMANENT

    def test_classify_http_503_overloaded(self):
        """Should classify 503 as overloaded."""
        reason = classify_provider_error(status=503, message="Server overloaded")
        assert reason == FailoverReason.OVERLOADED

    def test_classify_http_408_timeout(self):
        """Should classify 408 as timeout."""
        reason = classify_provider_error(status=408, message="Request timeout")
        assert reason == FailoverReason.TIMEOUT

    def test_classify_http_404_model_not_found(self):
        """Should classify 404 for model not found."""
        reason = classify_provider_error(status=404, message="Model not found")
        assert reason == FailoverReason.MODEL_NOT_FOUND

    def test_classify_message_pattern_billing(self):
        """Should classify billing from message pattern when status is None."""
        reason = classify_provider_error(
            status=None,  # No status - falls back to message pattern
            message="Insufficient credits",
        )
        assert reason == FailoverReason.BILLING

    def test_classify_message_pattern_rate_limit(self):
        """Should classify rate limit from message pattern when status is None."""
        reason = classify_provider_error(
            status=None,  # No status - falls back to message pattern
            message="Rate limit exceeded",
        )
        assert reason == FailoverReason.RATE_LIMIT

    def test_coerce_exception_to_failover_error(self):
        """Should coerce Exception to FailoverError."""
        error = Exception("401 Unauthorized")
        failover = coerce_to_failover_error(error, provider="anthropic")
        assert isinstance(failover, FailoverError)
        assert failover.reason == FailoverReason.AUTH

    def test_failover_error_is_transient(self):
        """Transient errors should be flagged."""
        error = FailoverError(
            reason=FailoverReason.RATE_LIMIT,
            provider="anthropic",
            model="claude-sonnet-4",
        )
        assert error.is_transient is True
        assert error.is_persistent is False

    def test_failover_error_is_persistent(self):
        """Persistent errors should be flagged."""
        error = FailoverError(
            reason=FailoverReason.BILLING,
            provider="anthropic",
            model="claude-sonnet-4",
        )
        assert error.is_transient is False
        assert error.is_persistent is True

    def test_failover_error_should_never_fallback(self):
        """Context overflow errors should not fallback."""
        error = FailoverError(
            reason=FailoverReason.MODEL_NOT_FOUND,
            provider="anthropic",
            model="invalid-model",
        )
        assert error.should_never_fallback is True


class TestTwoLaneCooldown:
    """Tests for the two-lane cooldown system."""

    def test_transient_cooldown_steps(self):
        """Should use stepped backoff for transient errors."""
        assert calculate_transient_cooldown(0) == 30_000
        assert calculate_transient_cooldown(1) == 60_000
        assert calculate_transient_cooldown(2) == 300_000
        assert calculate_transient_cooldown(10) == 300_000  # capped

    def test_persistent_cooldown_billing(self):
        """Should use exponential backoff for billing errors."""
        cooldown = calculate_persistent_cooldown(FailoverReason.BILLING, 0)
        assert cooldown == 5 * 60 * 60 * 1000  # 5 hours base

        cooldown = calculate_persistent_cooldown(FailoverReason.BILLING, 1)
        assert cooldown == 10 * 60 * 60 * 1000  # 10 hours

        cooldown = calculate_persistent_cooldown(FailoverReason.BILLING, 3)
        assert cooldown == 24 * 60 * 60 * 1000  # capped at 24 hours

    def test_two_lane_cooldown_apply_transient(self):
        """Should apply transient cooldown."""
        cooldown = TwoLaneCooldown()
        expiry = cooldown.apply_transient_cooldown(FailoverReason.RATE_LIMIT, 1)

        assert cooldown.transient_reason == FailoverReason.RATE_LIMIT
        assert cooldown.transient_cooldown_ms == 60_000
        assert cooldown.is_in_transient_cooldown() is True
        assert cooldown.is_usable() is False

    def test_two_lane_cooldown_apply_persistent(self):
        """Should apply persistent cooldown."""
        cooldown = TwoLaneCooldown()
        expiry = cooldown.apply_persistent_cooldown(FailoverReason.BILLING, 0)

        assert cooldown.persistent_reason == FailoverReason.BILLING
        assert cooldown.persistent_cooldown_ms == 5 * 60 * 60 * 1000
        assert cooldown.is_in_persistent_cooldown() is True
        assert cooldown.is_usable() is False

    def test_cooldown_clear_all(self):
        """Should clear all cooldowns."""
        cooldown = TwoLaneCooldown()
        cooldown.apply_transient_cooldown(FailoverReason.RATE_LIMIT, 1)
        cooldown.apply_persistent_cooldown(FailoverReason.BILLING, 0)

        cooldown.clear_all()

        assert cooldown.transient_cooldown_ms == 0
        assert cooldown.persistent_cooldown_ms == 0
        assert cooldown.is_usable() is True

    def test_model_scoped_rate_limit_bypass(self):
        """Should bypass rate limit for different models."""
        cooldown = TwoLaneCooldown()
        cooldown.apply_transient_cooldown(FailoverReason.RATE_LIMIT, 1)

        # Same model - don't bypass
        assert cooldown.should_bypass_model_cooldown("claude-sonnet", "claude-sonnet") is False

        # Different model - bypass
        assert cooldown.should_bypass_model_cooldown("claude-sonnet", "claude-opus") is True


class TestAuthProfiles:
    """Tests for auth profile management."""

    def test_auth_profile_store_add_profile(self):
        """Should add and retrieve a profile."""
        with TemporaryDirectory() as tmpdir:
            manager = AuthProfileStoreManager(Path(tmpdir) / "profiles.json")

            profile = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="test-key-1",
                    provider="anthropic",
                    type="api_key",
                    api_key="sk-ant-test-123",
                ),
            )

            manager.add_profile(profile)
            retrieved = manager.get_profile("test-key-1")

            assert retrieved is not None
            assert retrieved.credential.api_key == "sk-ant-test-123"
            assert retrieved.is_usable is True

    def test_auth_profile_mark_failure(self):
        """Should apply cooldown on failure."""
        with TemporaryDirectory() as tmpdir:
            manager = AuthProfileStoreManager(Path(tmpdir) / "profiles.json")

            profile = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="test-key-1",
                    provider="anthropic",
                    type="api_key",
                    api_key="sk-ant-test-123",
                ),
            )
            manager.add_profile(profile)

            # Mark failure
            manager.mark_profile_failure(
                "test-key-1",
                FailoverReason.RATE_LIMIT,
                cooldown_ms=30_000,
            )

            retrieved = manager.get_profile("test-key-1")
            assert retrieved is not None
            assert retrieved.is_usable is False
            assert retrieved.stats.error_count == 1

    def test_auth_profile_mark_success(self):
        """Should clear error count on success."""
        with TemporaryDirectory() as tmpdir:
            manager = AuthProfileStoreManager(Path(tmpdir) / "profiles.json")

            profile = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="test-key-1",
                    provider="anthropic",
                    type="api_key",
                    api_key="sk-ant-test-123",
                ),
            )
            manager.add_profile(profile)
            manager.mark_profile_failure("test-key-1", FailoverReason.RATE_LIMIT)
            manager.mark_profile_success("test-key-1")

            retrieved = manager.get_profile("test-key-1")
            assert retrieved is not None
            assert retrieved.stats.error_count == 0

    def test_get_ordered_profiles(self):
        """Should return profiles in rotation order."""
        with TemporaryDirectory() as tmpdir:
            manager = AuthProfileStoreManager(Path(tmpdir) / "profiles.json")

            # Add multiple profiles
            profile1 = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="oauth-key",
                    provider="anthropic",
                    type="oauth",
                    token="oauth-token",
                ),
            )
            profile2 = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="api-key-1",
                    provider="anthropic",
                    type="api_key",
                    api_key="key-1",
                ),
            )
            profile3 = AuthProfile(
                credential=AuthProfileCredential(
                    profile_id="api-key-2",
                    provider="anthropic",
                    type="api_key",
                    api_key="key-2",
                ),
            )

            manager.add_profile(profile1)
            manager.add_profile(profile2)
            manager.add_profile(profile3)

            ordered = manager.get_ordered_profiles("anthropic")

            # OAuth should be first (lowest priority number)
            assert ordered[0].credential.type == "oauth"
            assert ordered[0].profile_id == "oauth-key"


class TestFallbackPolicy:
    """Tests for fallback policy decisions."""

    def test_rotate_on_prompt_rate_limit(self):
        """Should rotate profile on rate limit."""
        decision = resolve_fallback_decision(
            stage=Stage.PROMPT,
            reason=FailoverReason.RATE_LIMIT,
            profile_rotated=False,
            fallback_configured=True,
            retry_count=0,
            max_retries=2,
        )

        assert decision.action == FallbackDecisionAction.ROTATE_PROFILE

    def test_fallback_on_exhausted_profiles(self):
        """Should fallback model after profile rotation exhausted."""
        decision = resolve_fallback_decision(
            stage=Stage.PROMPT,
            reason=FailoverReason.RATE_LIMIT,
            profile_rotated=True,  # Already rotated
            fallback_configured=True,
            retry_count=0,
            max_retries=2,
        )

        assert decision.action == FallbackDecisionAction.FALLBACK_MODEL

    def test_never_fallback_on_model_not_found(self):
        """Should never escalate on model not found (fallback won't help)."""
        decision = resolve_fallback_decision(
            stage=Stage.RETRY_LIMIT,  # At retry limit stage
            reason=FailoverReason.MODEL_NOT_FOUND,
            profile_rotated=True,
            fallback_configured=True,
            retry_count=2,
            max_retries=2,
        )

        # Should not escalate when retry limit reached and model won't be fixed by fallback
        assert decision.action == FallbackDecisionAction.RETURN_ERROR_PAYLOAD

    def test_fallback_disabled(self):
        """Should surface error when fallback is disabled."""
        policy = FallbackPolicy(fallback_enabled=False)
        decision = resolve_fallback_decision(
            stage=Stage.PROMPT,
            reason=FailoverReason.RATE_LIMIT,
            profile_rotated=True,
            fallback_configured=True,
            retry_count=0,
            max_retries=2,
            policy=policy,
        )

        assert decision.action == FallbackDecisionAction.SURFACE_ERROR


class TestCooldownDecisions:
    """Tests for cooldown decision logic."""

    def test_auth_never_probes(self):
        """Auth errors should never probe."""
        decision = resolve_cooldown_decision(
            reason=FailoverReason.AUTH,
            is_primary=True,
            has_fallback_candidates=False,
            cooldown_expiry=time.time() + 3600,
            requested_now=False,
            last_probe_at=None,
        )

        assert decision.type == "skip"

    def test_billing_primary_single_provider_probes(self):
        """Billing on primary with no fallback should probe."""
        decision = resolve_cooldown_decision(
            reason=FailoverReason.BILLING,
            is_primary=True,
            has_fallback_candidates=False,
            cooldown_expiry=time.time() + 3600,
            requested_now=True,
            last_probe_at=None,
        )

        assert decision.type == "attempt"

    def test_transient_same_provider_relaxes(self):
        """Transient errors on same-provider fallback should relax."""
        decision = resolve_cooldown_decision(
            reason=FailoverReason.RATE_LIMIT,
            is_primary=False,  # Same-provider fallback
            has_fallback_candidates=True,
            cooldown_expiry=time.time() + 30,
            requested_now=False,
            last_probe_at=None,
        )

        assert decision.type == "attempt"


class TestModelFallbackConfig:
    """Tests for model fallback configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = ModelFallbackConfig()
        assert config.enabled is True
        assert config.max_retries_per_model == 2
        assert config.max_total_attempts == 10
        assert config.use_auth_profiles is True

    def test_from_config(self):
        """Should parse from TenderClawConfig dict."""
        config_dict = {
            "experimental": {
                "advancedFallback": {
                    "enabled": True,
                    "fallbackModels": ["openai/gpt-5", "google/gemini-2.5"],
                    "maxRetriesPerModel": 3,
                }
            }
        }

        config = ModelFallbackConfig.from_config(config_dict)
        assert config.enabled is True
        assert "openai/gpt-5" in config.fallback_models
        assert config.max_retries_per_model == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
