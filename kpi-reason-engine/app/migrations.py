"""Alembic migration runner for the KPI reason engine."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _database_url(database_path: str) -> str:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def run_migrations(database_path: str) -> None:
    base_dir = Path(__file__).resolve().parent.parent
    script_location = base_dir / 'migrations'
    config = Config()
    config.set_main_option('script_location', str(script_location))
    config.set_main_option('sqlalchemy.url', _database_url(database_path))
    command.upgrade(config, 'head')
