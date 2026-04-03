"""Alembic migration runner for the TenderWriter backend."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


def _build_config(*, database_url: str | None = None) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    migrations_dir = backend_root / "migrations"
    ini_path = backend_root / "alembic.ini"

    resolved_database_url = str(database_url or settings.database_url).strip()
    if not resolved_database_url:
        raise RuntimeError("DATABASE_URL must be configured before running backend migrations.")

    config = Config(str(ini_path))
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("prepend_sys_path", str(backend_root))
    config.set_main_option("sqlalchemy.url", resolved_database_url.replace("%", "%%"))
    return config


def run_migrations(*, database_url: str | None = None, revision: str = "head") -> None:
    """Upgrade the backend database to the requested Alembic revision."""

    config = _build_config(database_url=database_url)
    command.upgrade(config, revision)
