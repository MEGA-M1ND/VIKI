from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from src.config import get_settings
from src.connectors.gmail import GmailConnector
from src.connectors.notion import NotionConnector
from src.gbrain_client.mcp_client import GBrainMCPClient
from src.pipeline.graph import build_extraction_graph
from src.pipeline.state import ExtractionState
from src.scheduler.cron import start_scheduler, stop_scheduler

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Company Brain API", version="0.1.0", lifespan=lifespan)

_last_ingestion: datetime | None = None
_ingestion_stats: dict = {"fetched": 0, "stored": 0, "skipped": 0}


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    client = GBrainMCPClient(settings)
    gmail = GmailConnector(settings)
    notion = NotionConnector(settings)

    gbrain_ok = await client.health()
    gmail_ok = await gmail.health_check()
    notion_ok = await notion.health_check()

    return {
        "status": "ok" if gbrain_ok else "degraded",
        "gbrain": gbrain_ok,
        "gmail": gmail_ok,
        "notion": notion_ok,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/auth/gmail")
async def auth_gmail() -> RedirectResponse:
    settings = get_settings()
    if not settings.gmail_client_id:
        raise HTTPException(status_code=400, detail="Gmail OAuth not configured")
    connector = GmailConnector(settings)
    auth_url = connector.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/gmail/callback")
async def auth_gmail_callback(code: str = Query(...)) -> dict:
    settings = get_settings()
    connector = GmailConnector(settings)
    try:
        connector.handle_oauth_callback(code)
        return {"status": "ok", "message": "Gmail OAuth token saved"}
    except Exception as exc:
        logger.error("api.gmail_callback_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest/run")
async def run_ingestion(hours: int = Query(default=24)) -> dict:
    global _last_ingestion, _ingestion_stats
    settings = get_settings()
    graph = build_extraction_graph()

    connectors = {
        "gmail": GmailConnector(settings),
        "notion": NotionConnector(settings),
    }

    fetched = stored = skipped = failed = 0

    for source_name, connector in connectors.items():
        log = logger.bind(source=source_name)
        try:
            async for doc in connector.fetch(lookback_hours=hours):
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
                    log.error("ingest.pipeline_error", source_id=doc.source_id, error=str(exc))
                    failed += 1
        except Exception as exc:
            log.error("ingest.connector_error", error=str(exc))

    _last_ingestion = datetime.now(tz=timezone.utc)
    _ingestion_stats = {"fetched": fetched, "stored": stored, "skipped": skipped, "failed": failed}
    logger.info("ingest.complete", **_ingestion_stats)
    return {"status": "complete", **_ingestion_stats}


@app.get("/brain/search")
async def brain_search(q: str = Query(..., description="Search query")) -> dict:
    settings = get_settings()
    client = GBrainMCPClient(settings)
    try:
        results = await client.search(q)
        return {"query": q, "results": results}
    except Exception as exc:
        logger.error("api.search_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brain/think")
async def brain_think(q: str = Query(..., description="Question to synthesize")) -> dict:
    settings = get_settings()
    client = GBrainMCPClient(settings)
    try:
        answer = await client.think(q)
        return {"query": q, "answer": answer}
    except Exception as exc:
        logger.error("api.think_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/brain/stats")
async def brain_stats() -> dict:
    settings = get_settings()
    connector_gmail = GmailConnector(settings)
    connector_notion = NotionConnector(settings)

    return {
        "last_ingestion": _last_ingestion.isoformat() if _last_ingestion else None,
        "ingestion_stats": _ingestion_stats,
        "sources": {
            "gmail": await connector_gmail.health_check(),
            "notion": await connector_notion.health_check(),
        },
    }
