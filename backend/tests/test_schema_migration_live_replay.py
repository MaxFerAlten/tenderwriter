"""Live replay checks for backend Alembic schema migrations.

These tests are opt-in because they require the local Docker stack to be up.
They exercise disposable PostgreSQL databases only and never touch the main
application database.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

RUN_LIVE_REPLAY = os.getenv("TW_RUN_LIVE_SCHEMA_REPLAY") == "1"
POSTGRES_CONTAINER = "tw-postgres"
POSTGRES_USER = "tenderwriter"
POSTGRES_PASSWORD = "DefaultPg2024Pass"
POSTGRES_HOST = "127.0.0.1"
POSTGRES_PORT = 5432
REVISION_ID = "20260403_0001"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE_REPLAY,
    reason="Set TW_RUN_LIVE_SCHEMA_REPLAY=1 to run live PostgreSQL schema replay tests.",
)


def _load_baseline_tables() -> tuple[str, ...]:
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260403_0001_backend_schema_baseline.py"
    )
    spec = importlib.util.spec_from_file_location("live_backend_schema_baseline", revision_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return tuple(module.BASELINE_TABLES)


def _docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _psql(database: str, sql: str) -> str:
    return _docker(
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-c",
        sql,
    )


def _run_local_migrations(database_name: str) -> str:
    database_url = (
        f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{database_name}"
    )
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
            "ADMIN_PASSWORD": "test-admin-password-1234567890",
            "DATABASE_URL": database_url,
            "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
            "MINIO_SECRET_KEY": "test-minio-password-1234567890",
            "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
            "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
            "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
        }
    )
    script = (
        "from app.db.migrations import run_migrations\n"
        f"run_migrations(database_url={database_url!r})\n"
        "print('migration-ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    return result.stdout.strip()


def _drop_database(database_name: str) -> None:
    _psql("postgres", f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE);')


def _create_database(database_name: str) -> None:
    _psql("postgres", f'CREATE DATABASE "{database_name}";')


def _table_names(database_name: str) -> set[str]:
    output = _psql(
        database_name,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name;",
    )
    return {line for line in output.splitlines() if line}


def _column_names(database_name: str, table_name: str) -> set[str]:
    output = _psql(
        database_name,
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = 'public' AND table_name = '{table_name}' ORDER BY column_name;",
    )
    return {line for line in output.splitlines() if line}


def test_live_upgrade_head_on_empty_database_creates_baseline_schema() -> None:
    """A disposable empty PostgreSQL database should upgrade cleanly to the backend baseline."""

    database_name = f"tw_schema_empty_{uuid.uuid4().hex[:10]}"
    baseline_tables = set(_load_baseline_tables())

    try:
        _create_database(database_name)
        output = _run_local_migrations(database_name)
        tables = _table_names(database_name)

        assert "migration-ok" in output
        assert baseline_tables.issubset(tables)
        assert "alembic_version" in tables
        assert _psql(database_name, "SELECT version_num FROM alembic_version;") == REVISION_ID
        assert {"is_active", "is_verified"} <= _column_names(database_name, "users")
        assert {"connection_method", "api_key"} <= _column_names(
            database_name, "ai_gateway_targets"
        )
    finally:
        _drop_database(database_name)


def test_live_upgrade_head_on_historical_shape_adds_compat_columns_and_missing_tables() -> None:
    """A simulated historical database should gain the compat columns and missing baseline tables."""

    database_name = f"tw_schema_hist_{uuid.uuid4().hex[:10]}"

    legacy_users_sql = """
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        role VARCHAR(50),
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ
    );
    CREATE UNIQUE INDEX ix_users_email ON users (email);
    CREATE INDEX ix_users_id ON users (id);
    """
    legacy_gateway_sql = """
    CREATE TABLE ai_gateway_targets (
        id SERIAL PRIMARY KEY,
        route_key VARCHAR(50) NOT NULL,
        target_kind VARCHAR(50) NOT NULL,
        provider VARCHAR(50) NOT NULL,
        base_url VARCHAR(500) NOT NULL,
        model_name VARCHAR(200),
        enabled BOOLEAN,
        priority INTEGER,
        timeout_ms INTEGER,
        use_anonymizer BOOLEAN,
        metadata_json JSONB,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ
    );
    CREATE INDEX ix_ai_gateway_targets_id ON ai_gateway_targets (id);
    """

    try:
        _create_database(database_name)
        _psql(database_name, legacy_users_sql)
        _psql(database_name, legacy_gateway_sql)

        output = _run_local_migrations(database_name)
        tables = _table_names(database_name)

        assert "migration-ok" in output
        assert {"is_active", "is_verified"} <= _column_names(database_name, "users")
        assert {"connection_method", "api_key"} <= _column_names(
            database_name, "ai_gateway_targets"
        )
        assert "content_blocks" in tables
        assert "alembic_version" in tables
        assert _psql(database_name, "SELECT version_num FROM alembic_version;") == REVISION_ID
    finally:
        _drop_database(database_name)
