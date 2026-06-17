"""Background scheduler.

Uses APScheduler's async backend to run periodic ingestion and health checks
in the same event loop as FastAPI. The scheduler is started/stopped via the
FastAPI lifespan context manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = get_logger(__name__)


class Scheduler:
    """Wraps APScheduler and exposes start/stop for the lifespan hook.

    Args:
        container: Service container providing connectors, extractor, and store.
        ingest_interval_minutes: How often to run incremental ingestion.
        health_interval_minutes: How often to run health checks.
    """

    def __init__(
        self,
        container: ServiceContainer,
        ingest_interval_minutes: int = 30,
        health_interval_minutes: int = 5,
    ) -> None:
        self._container = container
        self._ingest_interval = ingest_interval_minutes
        self._health_interval = health_interval_minutes
        self._scheduler: Any = None  # AsyncIOScheduler; typed Any to avoid hard dep

    def start(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError as exc:
            logger.warning("scheduler.apscheduler_missing", error=str(exc))
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_ingest,
            "interval",
            minutes=self._ingest_interval,
            id="ingest_all",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._run_health_check,
            "interval",
            minutes=self._health_interval,
            id="health_check",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "scheduler.started",
            ingest_minutes=self._ingest_interval,
            health_minutes=self._health_interval,
        )

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler.stopped")

    async def _run_ingest(self) -> None:
        logger.info("scheduler.ingest_triggered")
        container = self._container
        settings = container.settings

        # Only run if connectors are configured
        connectors = getattr(container, "connectors", [])
        if not connectors:
            logger.info("scheduler.no_connectors_configured")
            return

        from app.ingestion.orchestrator import IngestionOrchestrator

        extractor = container.extractor
        if extractor is None:
            logger.info("scheduler.no_extractor_configured")
            return

        for connector in connectors:
            orch = IngestionOrchestrator(connector, extractor, container.memory_store)
            try:
                stats = await orch.run(
                    tenant_id=settings.default_tenant_id,
                    lookback_hours=settings.ingestion_lookback_hours,
                )
                logger.info(
                    "scheduler.ingest_done",
                    source=stats.source,
                    fetched=stats.fetched,
                    ingested=stats.ingested,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("scheduler.ingest_failed", error=str(exc))

    async def _run_health_check(self) -> None:
        logger.info("scheduler.health_check_triggered")
        try:
            healthy = await self._container.memory_store.health_check()
            logger.info("scheduler.health_check_done", memory_store_healthy=healthy)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.health_check_failed", error=str(exc))
