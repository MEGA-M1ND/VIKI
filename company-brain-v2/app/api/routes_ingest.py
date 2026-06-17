"""Ingestion API routes.

POST /ingest/run  — trigger an ingestion run for a source
GET  /ingest/status — describe the last run's stats (in-memory only)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_container
from app.connectors.base import BaseConnector
from app.core.logging import get_logger
from app.ingestion.orchestrator import IngestionStats
from app.models.common import SourceType
from app.services.container import ServiceContainer

router = APIRouter(prefix="/ingest", tags=["ingestion"])
logger = get_logger(__name__)

# In-process store of recent run stats (keyed by source)
_last_stats: dict[str, IngestionStats] = {}


class IngestRunRequest(BaseModel):
    source: SourceType = Field(..., description="Which source to ingest from.")
    lookback_hours: int = Field(default=24, ge=1, le=168)
    dry_run: bool = Field(default=False)


class IngestRunResponse(BaseModel):
    source: str
    fetched: int
    normalized: int
    ingested: int
    skipped: int
    failed: int
    errors: dict[str, str]
    started_at: datetime


@router.post("/run", response_model=IngestRunResponse, status_code=status.HTTP_200_OK)
async def run_ingest(
    req: IngestRunRequest,
    container: ServiceContainer = Depends(get_container),
) -> IngestRunResponse:
    """Trigger an ingestion run for the given source."""
    from app.ingestion.orchestrator import IngestionOrchestrator

    connector = _get_connector(req.source, container)
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Connector for source '{req.source}' is not configured.",
        )

    extractor = container.extractor
    if extractor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No extractor is configured.",
        )

    orch = IngestionOrchestrator(connector, extractor, container.memory_store)
    stats = await orch.run(
        tenant_id=container.settings.default_tenant_id,
        lookback_hours=req.lookback_hours,
        dry_run=req.dry_run,
    )
    _last_stats[req.source] = stats
    logger.info("api.ingest_run", source=req.source, fetched=stats.fetched)

    return IngestRunResponse(
        source=stats.source,
        fetched=stats.fetched,
        normalized=stats.normalized,
        ingested=stats.ingested,
        skipped=stats.skipped,
        failed=stats.failed,
        errors=stats.errors,
        started_at=stats.started_at,
    )


@router.get("/status", response_model=dict[str, IngestRunResponse])
async def ingest_status() -> dict[str, IngestRunResponse]:
    """Return the stats from the last run per source."""
    return {
        src: IngestRunResponse(
            source=s.source,
            fetched=s.fetched,
            normalized=s.normalized,
            ingested=s.ingested,
            skipped=s.skipped,
            failed=s.failed,
            errors=s.errors,
            started_at=s.started_at,
        )
        for src, s in _last_stats.items()
    }


def _get_connector(source: SourceType, container: ServiceContainer) -> BaseConnector | None:
    for c in container.connectors:
        if getattr(c, "source", None) == source:
            return c
    return None
