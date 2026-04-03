"""Alembic environment for TenderWriter backend schema migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db.database import Base
import app.models  # noqa: F401  Ensures model metadata is registered.

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _configured_database_url() -> str:
    resolved_url = str(config.get_main_option("sqlalchemy.url") or "").strip()
    if not resolved_url:
        resolved_url = str(settings.database_url or "").strip()
    if not resolved_url:
        raise RuntimeError("DATABASE_URL must be configured before running backend migrations.")
    config.set_main_option("sqlalchemy.url", resolved_url.replace("%", "%%"))
    return resolved_url


def _database_url_is_async(resolved_database_url: str) -> bool:
    driver_name = make_url(resolved_database_url).drivername
    return driver_name in {"postgresql+asyncpg", "sqlite+aiosqlite"}


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    context.configure(
        url=_configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode using the backend async SQLAlchemy URL."""

    _configured_database_url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)

    await connectable.dispose()


def run_migrations_online_sync() -> None:
    """Run migrations in online mode using a synchronous SQLAlchemy driver."""

    _configured_database_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _run_sync_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    resolved_database_url = _configured_database_url()
    if _database_url_is_async(resolved_database_url):
        asyncio.run(run_migrations_online())
    else:
        run_migrations_online_sync()
