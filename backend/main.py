"""TenderClaw FastAPI application — entry point.

Wave 2 MVP bootstrap with startup hooks and persistence load.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
from backend.api.channels import router as channels_router
from backend.config import settings
from backend.migrations import run_all_pending
from backend.plugins.base import plugin_loader
from backend.services.session_store import session_store
from backend.tools.registry import tool_registry
from backend.tools.startup import register_builtin_tools
from backend.utils.logging import setup_logging
from backend.telemetry.tracing import setup_tracing, instrument_fastapi, shutdown_tracing
from backend.telemetry.metrics import setup_metrics, shutdown_metrics
from backend.telemetry.logging_config import setup_logging_with_tracing

logger = logging.getLogger("tenderclaw")

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown lifecycle."""
    if settings.otel_enabled:
        setup_logging_with_tracing(level=settings.log_level)
        setup_tracing(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_endpoint or None,
            console_export=not settings.otel_endpoint,
        )
        setup_metrics(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_endpoint or None,
            console_export=not settings.otel_endpoint,
        )
        instrument_fastapi(_app)
    else:
        setup_logging(settings.log_level)
    # Load persisted sessions into memory at startup (Wave 2 readiness)
    try:
        session_store.load_all_from_disk()
        logger.info("Persisted sessions loaded at startup (Wave 2 readiness)")
    except Exception as _exc:
        logger.warning("Failed to load persisted sessions at startup: %s", _exc)
    
    # Run settings migrations
    import backend.migrations.migrations  # noqa: F401
    run_all_pending()
    
    # Bootstrap Wave 2 MVP hooks (non-blocking in startup sequence)
    _init_hooks()
    register_builtin_tools(tool_registry)
    _load_custom_agents()

    # Initialize plugins
    _init_plugins()
    
    # Initialize channels (Telegram, Discord, etc.)
    _init_channels()
    
    logger.info(
        "TenderClaw started — http://%s:%d/tenderclaw",
        settings.host,
        settings.port,
    )
    yield
    await session_store.close_all()
    await _shutdown_channels()
    if settings.otel_enabled:
        shutdown_tracing()
        shutdown_metrics()
    logger.info("TenderClaw stopped")


def _load_custom_agents() -> None:
    """Load user-created agents from disk into the registry."""
    from backend.agents.registry import agent_registry
    from backend.services.custom_agent_store import custom_agent_store

    custom_agents = custom_agent_store.load_all()
    for agent in custom_agents:
        agent_registry.register(agent)
    if custom_agents:
        logger.info("Loaded %d custom agents from disk", len(custom_agents))


def _init_plugins() -> None:
    """Initialize plugin system."""
    from backend.agents.registry import agent_registry
    from backend.plugins.superpowers import SuperpowersPlugin
    
    try:
        plugin_loader.load_plugin(SuperpowersPlugin())
        plugin_loader.register_all(tool_registry, agent_registry)
        logger.info("Loaded %d plugins", len(plugin_loader._plugins))
    except FileNotFoundError:
        logger.warning("Superpowers plugin not found, skipping")


def _init_channels() -> None:
    """Initialize channel integrations (Telegram, Discord)."""
    from backend.api import channels
    
    if settings.telegram_bot_token:
        channels.telegram_manager.start()
        logger.info("Telegram channel initialized")
    
    if settings.discord_token:
        channels.discord_manager.start()
        logger.info("Discord channel initialized")


def _init_hooks() -> None:
    """Bootstrap Wave 2 MVP hooks."""
    try:
        from backend.hooks.initializer import bootstrap_hooks
        bootstrap_hooks()
        logger.info("Wave 2 MVP hooks bootstrap complete")
    except Exception as exc:
        logger.warning("Wave 2 MVP hooks bootstrap failed: %s", exc)


async def _shutdown_channels() -> None:
    """Shutdown all channel integrations."""
    from backend.api import channels
    
    await channels.telegram_manager.stop()
    await channels.discord_manager.stop()


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI app."""
    app = FastAPI(
        title="TenderClaw",
        version="0.1.0",
        description="Multi-agent, multi-model AI coding assistant",
        lifespan=lifespan,
    )

    if settings.dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix="/api")

    if FRONTEND_DIST.exists():
        app.mount(
            "/tenderclaw/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="frontend-assets",
        )

        @app.get("/tenderclaw")
        @app.get("/tenderclaw/{path:path}")
        async def serve_frontend(path: str = "") -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()


def run() -> None:
    """CLI entry point — `tenderclaw` command."""
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.dev,
    )


if __name__ == "__main__":
    run()
