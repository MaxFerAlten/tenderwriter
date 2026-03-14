"""Runtime configuration for tw-kpi-reason-engine."""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_prefix="KPI_REASON_ENGINE_",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
