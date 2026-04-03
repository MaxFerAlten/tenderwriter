import os
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover
    class BaseSettings(BaseModel):
        def __init__(self, **data: Any):
            super().__init__(**self._apply_env_defaults(data))

        @classmethod
        def _apply_env_defaults(cls, data: dict[str, Any]) -> dict[str, Any]:
            values = dict(data)
            prefix = "ANONYMIZER_"
            for field_name in cls.model_fields:
                env_key = f"{prefix}{field_name}".upper()
                if field_name not in values and env_key in os.environ:
                    values[field_name] = os.environ[env_key]
            return values

    def SettingsConfigDict(**kwargs: Any) -> dict[str, Any]:
        return kwargs


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANONYMIZER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8090
    redis_url: str = "memory://"
    admin_token: str = "tw-anonymizer-admin-token-change-me"
    ner_backend: str = "presidio_spacy"
    default_ttl_seconds: int = 3600
    default_strategy: str = "redaction"
    default_min_confidence: float = 0.35
    default_entities: list[str] = Field(
        default_factory=lambda: ["PERSON", "CODICE_FISCALE", "PARTITA_IVA", "IBAN"]
    )
    enable_cig_by_default: bool = False
    max_chunks: int = 32
    max_chunk_chars: int = 12000
    relay_timeout_seconds: float = 30.0

    def default_config(self) -> dict[str, Any]:
        return {
            "entities": list(self.default_entities),
            "ttl_seconds": self.default_ttl_seconds,
            "strategy": self.default_strategy,
            "min_confidence": self.default_min_confidence,
            "mask_cig": self.enable_cig_by_default,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
