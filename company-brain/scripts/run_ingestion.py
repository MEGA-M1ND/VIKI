#!/usr/bin/env python3
"""Manual ingestion trigger. Run with: python scripts/run_ingestion.py --source all"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from src.config import get_settings
from src.connectors.base import RawDocument
from src.connectors.gmail import GmailConnector
from src.connectors.notion import NotionConnector
from src.pipeline.graph import build_extraction_graph
from src.pipeline.state import ExtractionState

logger = structlog.get_logger("run_ingestion")

CONNECTOR_MAP = {
    "gmail": GmailConnector,
    "notion": NotionConnector,
}


async def run(source: str, hours: int, dry_run: bool) -> None:
    settings = get_settings()
    graph = build_extraction_graph()

    sources_to_run = list(CONNECTOR_MAP.keys()) if source == "all" else [source]

    totals = {"fetched": 0, "stored": 0, "skipped": 0, "failed": 0}
    rows: list[dict] = []

    for src_name in sources_to_run:
        connector_cls = CONNECTOR_MAP[src_name]
        connector = connector_cls(settings)
        print(f"\n[{src_name}] Fetching last {hours}h ...")

        try:
            async for doc in connector.fetch(lookback_hours=hours):
                totals["fetched"] += 1
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
                    if dry_run:
                        # Run all nodes except write
                        from src.pipeline.nodes import classify_node, extract_node, deduplicate_node

                        state = await classify_node(initial_state)
                        if state.get("is_worth_remembering"):
                            state = await extract_node(state)
                            state = await deduplicate_node(state)
                            status = "would_store" if not state.get("is_duplicate") else "would_skip_dup"
                        else:
                            status = "would_skip_classify"
                    else:
                        state = await graph.ainvoke(initial_state)
                        raw_status = state.get("write_status")
                        status = raw_status or "skipped"

                    rows.append(
                        {
                            "source": src_name,
                            "subject": (doc.subject or "")[:50],
                            "status": status,
                            "confidence": state.get("confidence") or 0.0,
                            "slug": state.get("gbrain_page_slug") or "-",
                        }
                    )

                    if status in ("success", "would_store"):
                        totals["stored"] += 1
                    elif status == "failed":
                        totals["failed"] += 1
                    else:
                        totals["skipped"] += 1

                except Exception as exc:
                    totals["failed"] += 1
                    rows.append(
                        {
                            "source": src_name,
                            "subject": (doc.subject or "")[:50],
                            "status": "ERROR",
                            "confidence": 0.0,
                            "slug": str(exc)[:50],
                        }
                    )

        except Exception as exc:
            print(f"  ERROR fetching from {src_name}: {exc}")

    # Print results table
    print("\n" + "=" * 80)
    mode_label = "[DRY RUN]" if dry_run else "[LIVE]"
    print(f"  INGESTION SUMMARY {mode_label}")
    print("=" * 80)
    print(f"  {'SOURCE':<12} {'SUBJECT':<52} {'STATUS':<18} {'CONF':>6}")
    print("-" * 80)
    for row in rows:
        print(
            f"  {row['source']:<12} {row['subject']:<52} {row['status']:<18} {row['confidence']:>6.2f}"
        )
    print("=" * 80)
    print(
        f"  Total: {totals['fetched']} fetched, "
        f"{totals['stored']} stored/would-store, "
        f"{totals['skipped']} skipped, "
        f"{totals['failed']} failed"
    )
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Company Brain manual ingestion trigger")
    parser.add_argument(
        "--source",
        choices=["gmail", "notion", "all"],
        default="all",
        help="Which source to ingest (default: all)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="How many hours to look back (default: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline but skip the write node",
    )
    args = parser.parse_args()

    asyncio.run(run(source=args.source, hours=args.hours, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
