"""Pre-fix diagnostics for backend schema migration readiness.

These tests intentionally capture the current structural gap before we touch
database bootstrap behavior. They give us a crisp pre-fix baseline for the
future Alembic rollout.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = BACKEND_ROOT / "app" / "db" / "database.py"
PYPROJECT_PATH = BACKEND_ROOT / "pyproject.toml"
MIGRATIONS_DIR = BACKEND_ROOT / "migrations"


def test_backend_declares_alembic_dependency() -> None:
    """The backend already ships Alembic as a dependency."""

    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert '"alembic>=' in pyproject


def test_backend_exposes_versioned_alembic_scaffold() -> None:
    """The backend should expose a real Alembic entrypoint and revisions directory."""

    ini_path = BACKEND_ROOT / "alembic.ini"
    env_path = MIGRATIONS_DIR / "env.py"
    versions_dir = MIGRATIONS_DIR / "versions"
    runner_path = BACKEND_ROOT / "app" / "db" / "migrations.py"
    versions_readme = versions_dir / "README.md"

    assert ini_path.exists()
    assert env_path.exists()
    assert versions_dir.is_dir()
    assert runner_path.exists()
    assert versions_readme.exists()


def test_backend_has_initial_baseline_revision() -> None:
    """The backend should ship an explicit initial schema revision."""

    revision_path = MIGRATIONS_DIR / "versions" / "20260403_0001_backend_schema_baseline.py"

    assert revision_path.exists()
    source = revision_path.read_text(encoding="utf-8")

    assert "revision = '20260403_0001'" in source
    assert "down_revision = None" in source
    assert "BASELINE_TABLES" in source
    assert "metadata = sa.MetaData()" in source
    assert "metadata.create_all(bind=bind, checkfirst=True)" in source
    assert "users" in source
    assert "ai_gateway_targets" in source


def test_init_db_no_longer_bootstraps_schema_opportunistically() -> None:
    """Schema ownership should move out of runtime bootstrap before the switch."""

    source = DATABASE_PATH.read_text(encoding="utf-8")
    init_db_block = source.split("async def init_db", 1)[1].split("async def close_db", 1)[0]

    assert "create_all" not in init_db_block
    assert "ALTER TABLE" not in init_db_block
    assert "IF NOT EXISTS" not in init_db_block
