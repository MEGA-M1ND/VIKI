"""FastAPI application entrypoint.

Builds the app, configures logging, wires the service container on startup, and
mounts routers. Run with ``make run-api`` or ``uvicorn app.main:app``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes_ask import router as ask_router
from app.api.routes_context import router as context_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_memory import router as memory_router
from app.api.routes_ui import router as ui_router
from app.api.routes_vc import router as vc_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.tenant import TenantMiddleware
from app.scheduler.cron import Scheduler
from app.services.container import ServiceContainer

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build collaborators on startup; release them on shutdown."""
    settings: Settings = get_settings()
    container = ServiceContainer.build(settings)
    app.state.container = container

    scheduler = Scheduler(
        container,
        ingest_interval_minutes=settings.ingestion_schedule_minutes,
        health_interval_minutes=settings.health_check_schedule_minutes,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    logger.info("app.startup", env=settings.app_env, name=settings.app_name)
    try:
        yield
    finally:
        scheduler.stop()
        logger.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Args:
        settings: Optional settings override (primarily for tests).

    Returns:
        A configured :class:`FastAPI` instance.
    """
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title="Company Brain",
        version="0.1.0",
        summary="A context layer for AI agents.",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    # Middleware (Starlette processes in reverse registration order — LIFO).
    # TenantMiddleware is added first so it executes last (i.e. after rate limit),
    # but since RateLimitMiddleware reads the header directly it doesn't need
    # the tenant_id from state, so order is effectively irrelevant here.
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RateLimitMiddleware)

    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(context_router)
    app.include_router(memory_router)
    app.include_router(ask_router)
    app.include_router(ui_router)
    app.include_router(vc_router)

    return app


app = create_app()


def run() -> None:
    """Console-script entrypoint (``company-brain``)."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
    )


if __name__ == "__main__":
    run()
