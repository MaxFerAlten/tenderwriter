"""
TenderWriter — Database Connection & Session Management
"""

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
    """Create all tables on startup (dev only — use Alembic in production)."""
    logger.info("Initializing database metadata")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Simple migrations for newly added columns if table already existed
        try:
            from sqlalchemy import text
            logger.info("Checking for missing compatibility columns")
            # Add is_active if missing
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
            # Add is_verified if missing
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE"))
            logger.info("Database schema compatibility check completed")
        except Exception as e:
            logger.warning("Database compatibility migration skipped", error=str(e))


async def close_db():
    """Dispose of the engine connection pool."""
    await engine.dispose()
