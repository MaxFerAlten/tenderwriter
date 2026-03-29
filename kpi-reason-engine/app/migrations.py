"""Alembic migration runner for the KPI reason engine."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _sqlite_database_url(database_path: str) -> str:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def run_migrations(*, database_url: str | None = None, database_path: str | None = None, schema_name: str | None = None) -> None:
    base_dir = Path(__file__).resolve().parent.parent
    script_location = base_dir / 'migrations'
    config = Config()
    config.set_main_option('script_location', str(script_location))
    resolved_database_url = (database_url or "").strip()
    if not resolved_database_url:
        if not database_path:
            raise RuntimeError('Either database_url or database_path must be provided for KPI migrations.')
        resolved_database_url = _sqlite_database_url(database_path)
    config.set_main_option('sqlalchemy.url', resolved_database_url)
    config.set_main_option('kpi.schema', str(schema_name or '').strip())
    command.upgrade(config, 'head')
