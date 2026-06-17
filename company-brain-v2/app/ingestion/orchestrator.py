"""Ingestion orchestrator.

Coordinates a connector → extractor → graph pipeline for one source and one
time window. Returns an :class:`IngestionStats` summary so callers (the API,
the scheduler, and CLI scripts) get a uniform view of what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger
from app.graphs.ingestion_graph import build_ingestion_graph
from app.ingestion.base import BaseExtractor
from app.memory.base import MemoryStore
from app.models.documents import RawDocument

logger = get_logger(__name__)


@dataclass
class IngestionStats:
    """Summary of one ingestion run.

    Attributes:
        fetched: Documents retrieved from the connector.
        normalized: Documents that passed validation and entered the pipeline.
        ingested: Documents for which at least one record was written.
        skipped: Documents that the pipeline determined were not worth storing
            (classified as unimportant, or produced no facts).
        failed: Documents that caused an unhandled error in the pipeline.
        errors: Short error descriptions keyed by document id.
    """

    source: str
    started_at: datetime = field(default_factory=lambda: __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc))
    fetched: int = 0
    normalized: int = 0
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.normalized == self.ingested + self.skipped + self.failed


class IngestionOrchestrator:
    """Run a full ingest cycle for one connector.

    Args:
        connector: The source connector to pull from.
        extractor: Extraction strategy (LLM, rules, …).
        store: Memory backend.
    """

    def __init__(
        self,
        connector: BaseConnector,
        extractor: BaseExtractor,
        store: MemoryStore,
    ) -> None:
        self._connector = connector
        self._extractor = extractor
        self._store = store
        self._graph = build_ingestion_graph(extractor, store)

    async def run(
        self,
        *,
        tenant_id: str,
        since: datetime | None = None,
        lookback_hours: int = 24,
        dry_run: bool = False,
    ) -> IngestionStats:
        """Execute one ingest cycle.

        Args:
            tenant_id: Tenant whose documents are being ingested.
            since: Only fetch documents modified after this time.
            lookback_hours: Lookback window when *since* is not provided.
            dry_run: If ``True``, run extraction but skip persistence.

        Returns:
            Stats describing what happened.
        """
        stats = IngestionStats(source=str(self._connector.source))
        logger.info(
            "orchestrator.run_started",
            source=stats.source,
            tenant_id=tenant_id,
            dry_run=dry_run,
        )

        try:
            docs = self._connector.fetch_documents(
                tenant_id=tenant_id,
                since=since,
                lookback_hours=lookback_hours,
            )
        except ConnectorError as exc:
            logger.error("orchestrator.fetch_failed", source=stats.source, error=str(exc))
            stats.errors["_fetch"] = str(exc)
            return stats

        async for doc in docs:
            stats.fetched += 1
            await self._process_document(doc, stats, dry_run=dry_run)

        logger.info(
            "orchestrator.run_finished",
            source=stats.source,
            **{k: getattr(stats, k) for k in ("fetched", "normalized", "ingested", "skipped", "failed")},
        )
        return stats

    async def _process_document(
        self, doc: RawDocument, stats: IngestionStats, *, dry_run: bool
    ) -> None:
        stats.normalized += 1
        if dry_run:
            logger.info("orchestrator.dry_run_skip", doc_id=doc.id)
            stats.skipped += 1
            return

        try:
            result = await self._graph.ainvoke({"document": doc})
            records = result.get("records") or []
            if records:
                stats.ingested += 1
            else:
                stats.skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("orchestrator.doc_failed", doc_id=doc.id, error=str(exc))
            stats.failed += 1
            stats.errors[doc.id] = str(exc)
