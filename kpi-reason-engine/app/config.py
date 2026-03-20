"""Runtime configuration for tw-kpi-reason-engine."""

from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_ROLLOUT_POLICIES = {"legacy", "shadow_only", "markov_only", "full"}


class Settings(BaseSettings):
    """Service configuration loaded from environment variables."""

    app_name: str = "tw-kpi-reason-engine"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8010
    log_level: str = "info"
    service_token: str = "changeme-kpi-service-token"
    public_base_url: str = "http://tw-kpi-reason-engine:8010"
    database_path: str = "/app/data/kpi_reason_engine.db"
    analysis_job_poll_interval_seconds: float = 0.25
    rollout_policy: str = "full"
    shadow_mode_enabled: bool = True
    semantic_official_enabled: bool = True
    markov_forecast_enabled: bool = True
    release_channel: str = "production"
    service_network_boundary: str = "internal_only"
    metrics_text_enabled: bool = True
    readiness_queue_warning_threshold: int = 5
    readiness_failed_jobs_threshold: int = 0
    readiness_snapshot_staleness_seconds: int = 21600

    model_config = SettingsConfigDict(
        env_prefix="KPI_REASON_ENGINE_",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def normalized_rollout_policy(self) -> str:
        normalized = str(self.rollout_policy or "full").strip().casefold()
        if normalized in _VALID_ROLLOUT_POLICIES:
            return normalized
        return "full"

    @property
    def semantic_shadow_rollout_enabled(self) -> bool:
        if not self.shadow_mode_enabled:
            return False
        return self.normalized_rollout_policy == "shadow_only"

    @property
    def semantic_official_rollout_enabled(self) -> bool:
        if not self.semantic_official_enabled:
            return False
        return self.normalized_rollout_policy == "full"

    @property
    def qualitative_engine_mode(self) -> str:
        if self.semantic_official_rollout_enabled:
            return "semantic_official"
        if self.semantic_shadow_rollout_enabled:
            return "shadow_control"
        return "proxy_only"

    @property
    def markov_rollout_enabled(self) -> bool:
        if not self.markov_forecast_enabled:
            return False
        return self.normalized_rollout_policy in {"markov_only", "full"}


settings = Settings()
