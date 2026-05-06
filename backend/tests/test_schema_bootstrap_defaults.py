"""Pre-switch defaults for schema bootstrap mode."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "backend" / "app" / "config.py"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


def test_code_and_deploy_defaults_prefer_alembic() -> None:
    """The default bootstrap path should eventually prefer Alembic while keeping an explicit legacy escape hatch."""

    config_source = CONFIG_PATH.read_text(encoding="utf-8")
    compose_source = COMPOSE_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert 'db_schema_bootstrap_mode: str = "alembic"' in config_source
    assert "DB_SCHEMA_BOOTSTRAP_MODE: ${DB_SCHEMA_BOOTSTRAP_MODE:-alembic}" in compose_source
    assert "DB_SCHEMA_BOOTSTRAP_MODE=alembic" in env_example
