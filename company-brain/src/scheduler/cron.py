import asyncio
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.connectors.gmail import GmailConnector
from src.connectors.notion import NotionConnector
from src.gbrain_client.mcp_client import GBrainMCPClient
from src.pipeline.graph import build_extraction_graph
from src.pipeline.state import ExtractionState

logger = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def ingest_all_sources() -> None:
    settings = get_settings()
    graph = build_extraction_graph()
    log = logger.bind(job="ingest_all_sources")

    connectors = {
        "gmail": GmailConnector(settings),
        "notion": NotionConnector(settings),
    }

    fetched = stored = skipped = failed = 0

    for source_name, connector in connectors.items():
        src_log = log.bind(source=source_name)
        try:
            async for doc in connector.fetch(lookback_hours=settings.ingestion_lookback_hours):
                fetched += 1
                initial_state: ExtractionState = {
                    "document": doc,
                    "is_worth_remembering": None,
                    "classifier_reasoning": None,
                    "confidence": None,
                    "extracted_facts": None,
                    "entities": None,
                    "summary": None,
                    "existing_similar_pages": None,
                    "is_duplicate": None,
                    "gbrain_page_slug": None,
                    "write_status": None,
                    "error": None,
                }
                try:
                    result = await graph.ainvoke(initial_state)
                    status = result.get("write_status")
                    if status == "success":
                        stored += 1
                    elif status == "failed":
                        failed += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    src_log.error("cron.pipeline_error", source_id=doc.source_id, error=str(exc))
                    failed += 1
        except Exception as exc:
            src_log.error("cron.connector_error", error=str(exc))

    log.info(
        "cron.ingest_complete",
        fetched=fetched,
        stored=stored,
        skipped=skipped,
        failed=failed,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


async def health_check_all() -> None:
    settings = get_settings()
    log = logger.bind(job="health_check_all")

    client = GBrainMCPClient(settings)
    gmail = GmailConnector(settings)
    notion = NotionConnector(settings)

    gbrain_ok = await client.health()
    gmail_ok = await gmail.health_check()
    notion_ok = await notion.health_check()

    log.info(
        "cron.health_check",
        gbrain=gbrain_ok,
        gmail=gmail_ok,
        notion=notion_ok,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(ingest_all_sources, "interval", minutes=30, id="ingest_all_sources")
    scheduler.add_job(health_check_all, "interval", minutes=5, id="health_check_all")
    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler.started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")
    _scheduler = None
