"""
TenderWriter — FastAPI Application Entry Point
"""

import asyncio
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    try:
        logger.info(
            "Starting TenderWriter",
            version=settings.app_version,
            debug=settings.app_debug,
        )

        from app.db.database import async_session_factory, init_db
        from app.models import User
        from sqlalchemy import select
        from app.api.auth import hash_password

        await init_db()
        logger.info("Database initialized")

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.email == settings.admin_username))
            admin_user = result.scalar_one_or_none()

            if admin_user:
                if not settings.admin_enabled:
                    if admin_user.is_active:
                        admin_user.is_active = False
                        await session.commit()
                        logger.info("Admin user disabled by configuration")
                else:
                    if not admin_user.is_active or not admin_user.is_verified:
                        admin_user.is_active = True
                        admin_user.is_verified = True
                        await session.commit()
                        logger.info("Admin user forced to active/verified status")
            elif settings.admin_enabled:
                admin_user = User(
                    email=settings.admin_username,
                    name="System Admin",
                    hashed_password=hash_password(settings.admin_password),
                    role="admin",
                    is_active=True,
                    is_verified=True,
                )
                session.add(admin_user)
                await session.commit()
                logger.info(f"Admin user '{settings.admin_username}' created successfully")

        from app.rag.engine import HybridRAGEngine

        app.state.rag_engine = HybridRAGEngine()
        app.state.rag_engine_initialization_task = None
        logger.info("HybridRAG engine ready for lazy initialization")

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Startup failed: {e}")
        raise e

    yield

    try:
        logger.info("Shutting down TenderWriter")
        init_task = getattr(app.state, "rag_engine_initialization_task", None)
        if init_task and not init_task.done():
            init_task.cancel()
            with suppress(asyncio.CancelledError):
                await init_task
        if hasattr(app.state, "rag_engine"):
            await app.state.rag_engine.shutdown()
        from app.db.redis import close_redis
        from app.db.database import close_db
        await close_redis()
        await close_db()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Open-source Tender Proposal Software with HybridRAG",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.auth import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    from app.api import admin, anonymizer_admin, auth, chat, content_library, gateway_admin, kpi_admin, observability, onlyoffice, proposals, rag, system, tenders
    from app.api.tasks import router as tasks_router

    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(system.router, prefix="/api/system", tags=["System Dashboard"])
    app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
    app.include_router(anonymizer_admin.router, prefix="/api/anonymizer", tags=["Anonymizer"])
    app.include_router(kpi_admin.router, prefix="/api/admin/kpi", tags=["Admin KPI"])
    app.include_router(gateway_admin.router, prefix="/api/gateway", tags=["Gateway"])
    app.include_router(onlyoffice.router, prefix="/api/onlyoffice", tags=["OnlyOffice"])
    app.include_router(tenders.router, prefix="/api/tenders", tags=["Tenders"])
    app.include_router(observability.router, prefix="/api/tenders", tags=["Operational Observability"])
    app.include_router(chat.router, prefix="/api/tenders", tags=["Tender Chat"])
    app.include_router(proposals.router, prefix="/api/proposals", tags=["Proposals"])
    app.include_router(content_library.router, prefix="/api/content-blocks", tags=["Content Library"])
    app.include_router(rag.router, prefix="/api/rag", tags=["RAG"])
    app.include_router(tasks_router, prefix="/api/tasks", tags=["Tasks"])

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    return app


app = create_app()
