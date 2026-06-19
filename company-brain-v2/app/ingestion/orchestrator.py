"""Ingestion orchestrator.

Coordinates a connector → extractor → graph pipeline for one source and one
time window. Returns an :class:`IngestionStats` summary so callers (the API,
the scheduler, and CLI scripts) get a uniform view of what happened.

Phase 2.5 adds an optional VC extraction pass (_run_vc_pass) that runs after
the primary graph when both an LLM and a VC repository are configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger
from app.graphs.ingestion_graph import build_ingestion_graph
from app.ingestion.base import BaseExtractor
from app.llm.base import LLMProvider
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
        connector: The source connector to pull from. May be None for direct
            document ingestion (e.g. via the /ingest/document endpoint).
        extractor: Extraction strategy (LLM, rules, …).
        store: Memory backend.
        llm: Optional LLM provider for the VC extraction pass.
        vc_repo: Optional VC repository for storing extracted VC facts.
    """

    def __init__(
        self,
        connector: BaseConnector | None,
        extractor: BaseExtractor,
        store: MemoryStore,
        llm: LLMProvider | None = None,
        vc_repo: object | None = None,
    ) -> None:
        self._connector = connector
        self._extractor = extractor
        self._store = store
        self._llm = llm
        self._vc_repo = vc_repo
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
        if self._connector is None:
            raise ConnectorError("No connector configured for run().")

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

    async def ingest_single(self, doc: RawDocument) -> dict:
        """Ingest a single document directly (bypasses connector).

        Runs the full graph (extract → persist) and optionally the VC pass.

        Args:
            doc: The document to ingest.

        Returns:
            A dict with ``ingested`` and ``skipped`` counts.
        """
        stats = IngestionStats(source=str(doc.source))
        await self._process_document(doc, stats, dry_run=False)
        return {"ingested": stats.ingested, "skipped": stats.skipped}

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
                if self._llm and self._vc_repo:
                    await self._run_vc_pass(doc)
            else:
                stats.skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("orchestrator.doc_failed", doc_id=doc.id, error=str(exc))
            stats.failed += 1
            stats.errors[doc.id] = str(exc)

    async def _run_vc_pass(self, doc: RawDocument) -> None:
        """Run the VC-aware extraction pass and populate VC tables.

        Args:
            doc: The document that was successfully ingested.
        """
        from app.db.vc_repo import VCRepository
        from app.models.vc import FundSignal
        from app.prompts.extraction import build_vc_extract_messages, parse_vc_extraction
        from app.scoring.founder import FounderSignalScorer
        from app.utils.ids import utcnow

        assert self._llm is not None  # type narrowing
        assert self._vc_repo is not None
        vc_repo: VCRepository = self._vc_repo  # type: ignore[assignment]

        messages = build_vc_extract_messages(
            source=str(doc.source),
            title=doc.title or "",
            author=doc.author or "",
            content=doc.content,
        )
        try:
            raw = await self._llm.chat(messages, json_mode=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("vc_pass.llm_failed", doc_id=doc.id, error=str(exc))
            return

        vc_facts = parse_vc_extraction(raw)
        if not vc_facts:
            return

        scorer = FounderSignalScorer()
        for fact in vc_facts:
            fact_type = fact.get("fact_type", "")
            if fact_type == "FOUNDER_SIGNAL":
                founder = await vc_repo.upsert_founder_from_signal(
                    tenant_id=doc.tenant_id,
                    vc_fact=fact,
                    source_doc_id=doc.id,
                )
                existing_signals = await vc_repo.get_signals_for_founder(
                    tenant_id=doc.tenant_id, founder_id=founder.id
                )
                new_score = scorer.score(founder, existing_signals)
                await vc_repo.update_founder_score(
                    tenant_id=doc.tenant_id, founder_id=founder.id, score=new_score
                )
                logger.info(
                    "vc_pass.founder_upserted",
                    founder_id=str(founder.id),
                    score=new_score,
                )
            elif fact_type == "JOB_OPPORTUNITY":
                # Store as a fund signal with type "outreach"
                await vc_repo.add_signal(
                    FundSignal(
                        tenant_id=doc.tenant_id,
                        signal_type="outreach",
                        company_name=fact.get("entities", {}).get("company", "unknown"),
                        signal_date=utcnow(),
                        raw_text=fact.get("statement", ""),
                        confidence=float(fact.get("confidence", 0.5)),
                    )
                )
