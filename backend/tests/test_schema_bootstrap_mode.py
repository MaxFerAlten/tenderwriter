"""Regression tests for explicit schema bootstrap mode selection."""

from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


class _FakeConnection:
    def __init__(self) -> None:
        self.run_sync = AsyncMock()
        self.execute = AsyncMock()


class _FakeBeginContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()
        self.begin_calls = 0

    def begin(self):
        self.begin_calls += 1
        return _FakeBeginContext(self.connection)


def test_init_db_supports_explicit_alembic_bootstrap_mode() -> None:
    """init_db should be able to delegate schema ownership to Alembic explicitly."""

    fake_engine = _FakeEngine()
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        database_url="postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
        app_debug=False,
        db_schema_bootstrap_mode="alembic",
    )
    fake_migrations = ModuleType("app.db.migrations")
    fake_migrations.run_migrations = Mock()
    fake_to_thread = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("asyncio.to_thread", fake_to_thread),
        patch.dict(
            sys.modules,
            {
                "app.config": fake_config,
                "app.db.migrations": fake_migrations,
            },
        ),
    ):
        sys.modules.pop("app.db.database", None)
        database_module = import_module("app.db.database")
        asyncio.run(database_module.init_db())

    fake_to_thread.assert_awaited_once_with(
        fake_migrations.run_migrations,
        database_url="postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    )
    fake_migrations.run_migrations.assert_not_called()
    assert fake_engine.begin_calls == 0


def test_init_db_metadata_compat_mode_delegates_to_alembic_for_backward_compatibility() -> None:
    """The legacy mode name should remain usable while delegating to Alembic."""

    fake_engine = _FakeEngine()
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        database_url="postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
        app_debug=False,
        db_schema_bootstrap_mode="metadata_compat",
    )
    fake_migrations = ModuleType("app.db.migrations")
    fake_migrations.run_migrations = Mock()
    fake_to_thread = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("asyncio.to_thread", fake_to_thread),
        patch.dict(
            sys.modules,
            {
                "app.config": fake_config,
                "app.db.migrations": fake_migrations,
            },
        ),
    ):
        sys.modules.pop("app.db.database", None)
        database_module = import_module("app.db.database")
        asyncio.run(database_module.init_db())

    fake_to_thread.assert_awaited_once_with(
        fake_migrations.run_migrations,
        database_url="postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    )
    fake_migrations.run_migrations.assert_not_called()
    assert fake_engine.begin_calls == 0
