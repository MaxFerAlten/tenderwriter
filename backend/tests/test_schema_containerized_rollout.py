"""Containerized rollout smoke tests for Alembic bootstrap mode.

These tests are opt-in because they invoke `docker compose run` against the
local stack. They only use disposable PostgreSQL databases.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

RUN_CONTAINERIZED_ROLLOUT = os.getenv("TW_RUN_DOCKER_SCHEMA_ROLLOUT") == "1"
REPO_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_CONTAINER = "tw-postgres"
POSTGRES_USER = "tenderwriter"
POSTGRES_PASSWORD = "DefaultPg2024Pass"
POSTGRES_DB_HOST = "postgres"
POSTGRES_PORT = 5432
REVISION_ID = "20260408_0007"

pytestmark = pytest.mark.skipif(
    not RUN_CONTAINERIZED_ROLLOUT,
    reason="Set TW_RUN_DOCKER_SCHEMA_ROLLOUT=1 to run docker compose rollout smoke tests.",
)


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        cwd=str(cwd or REPO_ROOT),
    )
    return result.stdout.strip()


def _docker_exec_psql(database: str, sql: str) -> str:
    return _run(
        [
            "docker",
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
        ]
    )


def _drop_database(database_name: str) -> None:
    _docker_exec_psql("postgres", f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE);')


def _create_database(database_name: str) -> None:
    _docker_exec_psql("postgres", f'CREATE DATABASE "{database_name}";')


def _column_names(database_name: str, table_name: str) -> set[str]:
    output = _docker_exec_psql(
        database_name,
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = 'public' AND table_name = '{table_name}' ORDER BY column_name;",
    )
    return {line for line in output.splitlines() if line}


def test_backend_one_off_container_bootstraps_via_alembic_mode() -> None:
    """A one-off backend container should initialize a disposable DB via Alembic mode."""

    database_name = f"tw_schema_rollout_{uuid.uuid4().hex[:10]}"
    database_url = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_DB_HOST}:{POSTGRES_PORT}/{database_name}"
    )

    try:
        _create_database(database_name)
        output = _run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL={database_url}",
                "-e",
                "DB_SCHEMA_BOOTSTRAP_MODE=alembic",
                "backend",
                "python",
                "-c",
                (
                    "import asyncio; "
                    "from app.db.database import init_db; "
                    "asyncio.run(init_db()); "
                    "print('bootstrap-ok')"
                ),
            ]
        )

        assert "bootstrap-ok" in output
        assert _docker_exec_psql(database_name, "SELECT version_num FROM alembic_version;") == REVISION_ID
        assert {"is_active", "is_verified"} <= _column_names(database_name, "users")
        assert {"connection_method", "api_key"} <= _column_names(
            database_name, "ai_gateway_targets"
        )
    finally:
        _drop_database(database_name)


def test_backend_one_off_container_uses_alembic_deploy_default() -> None:
    """A one-off backend container should use the compose/default Alembic mode without an explicit override."""

    database_name = f"tw_schema_default_{uuid.uuid4().hex[:10]}"
    database_url = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_DB_HOST}:{POSTGRES_PORT}/{database_name}"
    )

    try:
        _create_database(database_name)
        output = _run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL={database_url}",
                "backend",
                "python",
                "-c",
                (
                    "import asyncio; "
                    "from app.db.database import init_db; "
                    "asyncio.run(init_db()); "
                    "print('bootstrap-ok')"
                ),
            ]
        )

        assert "bootstrap-ok" in output
        assert _docker_exec_psql(database_name, "SELECT version_num FROM alembic_version;") == REVISION_ID
    finally:
        _drop_database(database_name)


def test_backend_one_off_container_keeps_metadata_compat_as_alembic_alias() -> None:
    """An explicit metadata_compat override should still work while delegating to Alembic."""

    database_name = f"tw_schema_compat_{uuid.uuid4().hex[:10]}"
    database_url = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_DB_HOST}:{POSTGRES_PORT}/{database_name}"
    )

    try:
        _create_database(database_name)
        output = _run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL={database_url}",
                "-e",
                "DB_SCHEMA_BOOTSTRAP_MODE=metadata_compat",
                "backend",
                "python",
                "-c",
                (
                    "import asyncio; "
                    "from app.db.database import init_db; "
                    "asyncio.run(init_db()); "
                    "print('bootstrap-ok')"
                ),
            ]
        )

        assert "bootstrap-ok" in output
        assert _docker_exec_psql(database_name, "SELECT version_num FROM alembic_version;") == REVISION_ID
    finally:
        _drop_database(database_name)
