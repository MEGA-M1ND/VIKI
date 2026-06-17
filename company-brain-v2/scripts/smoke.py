#!/usr/bin/env python3
"""Local smoke test: run a document through the full skeleton, no network.

Usage:
    python scripts/smoke.py

Exercises connectors-less ingestion: a hand-built RawDocument -> fake-extractor
-> ingestion graph -> in-memory store -> context provider. Useful for verifying
the wiring after changes without booting the API.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running directly (`python scripts/smoke.py`) without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.provider import MemoryContextProvider
from app.core.logging import configure_logging, get_logger
from app.graphs.ingestion_graph import build_ingestion_graph
from app.ingestion.base import BaseExtractor
from app.memory.in_memory import InMemoryStore
from app.models import ExtractedFact, RawDocument, SourceType

logger = get_logger("smoke")


class EchoExtractor(BaseExtractor):
    """Reference extractor: emits a single fact per document."""

    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        return [
            ExtractedFact(
                document_id=document.id,
                tenant_id=document.tenant_id,
                source=document.source,
                statement=document.content,
            )
        ]


async def main() -> None:
    configure_logging(level="INFO", json_logs=False)
    store = InMemoryStore()
    graph = build_ingestion_graph(EchoExtractor(), store)

    doc = RawDocument(
        source=SourceType.GMAIL,
        source_id="demo-1",
        content="Alice approved the Q2 budget of $500k for infra.",
        title="Q2 Budget",
        author="alice@example.com",
    )

    state = await graph.ainvoke({"document": doc})
    logger.info("smoke.ingested", records=len(state["records"]))

    provider = MemoryContextProvider(store)
    context = await provider.build_context(tenant_id="default", query="budget approval")

    print("\n--- Injected context ---")
    print(context or "(empty)")
    print("------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
