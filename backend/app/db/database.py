"""
TenderWriter — Database Connection & Session Management
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=20,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


async def get_db() -> AsyncSession:
    """Dependency for FastAPI routes — yields a database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialize schema according to the configured bootstrap mode."""
    bootstrap_mode = str(getattr(settings, "db_schema_bootstrap_mode", "alembic")).strip().lower()

    if bootstrap_mode in {"alembic", "metadata_compat"}:
        if bootstrap_mode == "metadata_compat":
            logger.warning(
                "DB_SCHEMA_BOOTSTRAP_MODE=metadata_compat is deprecated; delegating to Alembic migrations"
            )
        else:
            logger.info("Initializing database schema via Alembic migrations")

        from app.db.migrations import run_migrations

        await asyncio.to_thread(run_migrations, database_url=settings.database_url)
        return

    raise RuntimeError(
        f"Unsupported DB_SCHEMA_BOOTSTRAP_MODE: {settings.db_schema_bootstrap_mode!r}"
    )


async def close_db():
    """Dispose of the engine connection pool."""
    await engine.dispose()
