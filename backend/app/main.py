"""
TenderWriter — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

        # Initialize database connection pool
        from app.db.database import init_db
        await init_db()
        logger.info("Database initialized")

        # Initialize RAG engine components
        from app.rag.engine import HybridRAGEngine
        app.state.rag_engine = HybridRAGEngine()
        await app.state.rag_engine.initialize()
        logger.info("HybridRAG engine initialized")

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Startup failed: {e}")
        # We might want to re-raise to fail the container, but printing is key for now
        raise e

    yield

    # Shutdown
    try:
        logger.info("Shutting down TenderWriter")
        if hasattr(app.state, "rag_engine"):
            await app.state.rag_engine.shutdown()
        from app.db.database import close_db
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

    # CORS
    origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    from app.api import tenders, proposals, content_library, rag, auth

    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(tenders.router, prefix="/api/tenders", tags=["Tenders"])
    app.include_router(proposals.router, prefix="/api/proposals", tags=["Proposals"])
    app.include_router(
        content_library.router, prefix="/api/content-blocks", tags=["Content Library"]
    )
    app.include_router(rag.router, prefix="/api/rag", tags=["RAG"])

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    return app


app = create_app()
