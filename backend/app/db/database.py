"""
TenderWriter — Database Connection & Session Management
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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
    print("DEBUG: Initializing database...", flush=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Simple migrations for newly added columns if table already existed
        try:
            from sqlalchemy import text
            print("DEBUG: Checking for missing columns in 'users' table...", flush=True)
            # Add is_active if missing
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
            # Add is_verified if missing
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE"))
            print("DEBUG: Database schema check completed.", flush=True)
        except Exception as e:
            print(f"DEBUG: Migration error (ignoring): {e}", flush=True)
            pass


async def close_db():
    """Dispose of the engine connection pool."""
    await engine.dispose()
