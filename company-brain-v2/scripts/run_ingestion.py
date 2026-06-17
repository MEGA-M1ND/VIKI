#!/usr/bin/env python3
"""CLI script: run an ingestion cycle for one or all sources.

Usage:
    python scripts/run_ingestion.py --source gmail --hours 48
    python scripts/run_ingestion.py --source all --dry-run
    python scripts/run_ingestion.py --source notion
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.ingestion.orchestrator import IngestionOrchestrator

logger = get_logger("run_ingestion")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Company Brain ingestion.")
    parser.add_argument(
        "--source",
        choices=["gmail", "notion", "all"],
        default="all",
        help="Which source to ingest from.",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Look-back window in hours.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and classify but skip persistence.",
    )
    return parser.parse_args()


async def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=False)

    args = parse_args()

    from app.ingestion.base import BaseExtractor
    from app.memory.factory import build_memory_store
    from app.models import ExtractedFact, RawDocument

    # Build a minimal extractor for the CLI (no LLM needed for smoke test)
    class PassthroughExtractor(BaseExtractor):
        async def extract(self, document: RawDocument) -> list[ExtractedFact]:
            from app.models import ExtractedFact

            return [
                ExtractedFact(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    source=document.source,
                    statement=document.content[:200],
                )
            ]

    store = build_memory_store(settings)
    extractor = PassthroughExtractor()

    connectors = _build_connectors(args.source, settings)
    if not connectors:
        logger.error("run_ingestion.no_connectors", source=args.source)
        sys.exit(1)

    for connector in connectors:
        orch = IngestionOrchestrator(connector, extractor, store)
        stats = await orch.run(
            tenant_id=settings.default_tenant_id,
            lookback_hours=args.hours,
            dry_run=args.dry_run,
        )
        print(f"\n--- {stats.source} ---")
        print(f"  Fetched:    {stats.fetched}")
        print(f"  Normalized: {stats.normalized}")
        print(f"  Ingested:   {stats.ingested}")
        print(f"  Skipped:    {stats.skipped}")
        print(f"  Failed:     {stats.failed}")
        if stats.errors:
            print(f"  Errors:     {stats.errors}")


def _build_connectors(source: str, settings: object) -> list:
    from app.connectors.gmail import GmailConnector
    from app.connectors.notion import NotionConnector

    connectors = []
    if source in ("gmail", "all"):
        connectors.append(
            GmailConnector(
                client_id=getattr(settings, "gmail_client_id", ""),
                client_secret=getattr(settings, "gmail_client_secret", ""),
            )
        )
    if source in ("notion", "all"):
        connectors.append(
            NotionConnector(
                token=getattr(settings, "notion_api_key", "") or getattr(settings, "notion_token", ""),
                database_ids=[
                    i.strip()
                    for i in getattr(settings, "notion_database_ids", "").split(",")
                    if i.strip()
                ],
            )
        )
    return connectors


if __name__ == "__main__":
    asyncio.run(main())
