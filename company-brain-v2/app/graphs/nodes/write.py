"""Write node.

Converts deduplicated :class:`~app.models.facts.ExtractedFact` objects into
:class:`~app.models.memory.MemoryRecord` entries and persists them. Facts that
cannot be written are serialised to a dead-letter file (``failed_writes.jsonl``)
so they can be retried or inspected without being silently dropped.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.exceptions import WriteFailureError
from app.core.logging import get_logger
from app.graphs.nodes.dedupe import _dedupe_key
from app.graphs.state import PipelineState
from app.memory.base import MemoryStore
from app.models.facts import ExtractedFact
from app.models.memory import MemoryRecord

logger = get_logger(__name__)

_DEAD_LETTER_PATH = Path("failed_writes.jsonl")


def _fact_to_record(fact: ExtractedFact) -> MemoryRecord:
    return MemoryRecord(
        tenant_id=fact.tenant_id,
        content=fact.statement,
        record_type=fact.fact_type,
        source=fact.source,
        source_refs=[fact.document_id, fact.id],
        metadata={
            "confidence": fact.confidence,
            "dedupe_key": _dedupe_key(fact),
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object_,
            "tags": fact.tags,
            "validity_kind": str(fact.validity_kind),
        },
    )


def _write_dead_letter(fact: ExtractedFact, error: str, path: Path) -> None:
    entry = {"fact_id": fact.id, "statement": fact.statement, "error": error}
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def make_write_node(
    store: MemoryStore, dead_letter_path: Path = _DEAD_LETTER_PATH
) -> Callable[[PipelineState], Awaitable[dict]]:
    """Return a write node that persists to *store*."""

    async def write_node(state: PipelineState) -> dict:
        new_facts = state.get("new_facts") or []
        records: list[MemoryRecord] = []
        failed_facts: list[dict] = list(state.get("failed_facts") or [])

        for fact in new_facts:
            record = _fact_to_record(fact)
            try:
                stored = await store.write(record)
                records.append(stored)
            except Exception as exc:  # noqa: BLE001
                err_msg = str(exc)
                logger.error("write.failed", fact_id=fact.id, error=err_msg)
                _write_dead_letter(fact, err_msg, dead_letter_path)
                failed_facts.append({"fact_id": fact.id, "error": err_msg})
                raise WriteFailureError(
                    f"Failed to write fact {fact.id}",
                    details={"fact_id": fact.id, "destination": str(dead_letter_path)},
                ) from exc

        logger.info("write.done", records=len(records), failed=len(failed_facts))
        return {**state, "records": records, "failed_facts": failed_facts}

    return write_node
