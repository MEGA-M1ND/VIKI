"""Default :class:`ContextProvider` backed by a :class:`MemoryStore`.

Retrieves ranked memory and renders a compact, deterministic context block.
No LLM is involved — synthesis (e.g. summarization) can be layered on later
behind the same interface.
"""

from __future__ import annotations

from app.context.base import ContextProvider
from app.core.exceptions import ContextError
from app.core.logging import get_logger
from app.memory.base import MemoryStore
from app.models.retrieval import RetrievalQuery, RetrievalResult

logger = get_logger(__name__)


class MemoryContextProvider(ContextProvider):
    """Builds agent context by retrieving from a memory store and formatting it."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def retrieve(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievalResult]:
        try:
            return await self._store.query(
                RetrievalQuery(tenant_id=tenant_id, text=query, limit=limit)
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as domain error
            logger.error("context.retrieve_failed", tenant=tenant_id, error=str(exc))
            raise ContextError("Failed to retrieve context", details={"query": query}) from exc

    async def build_context(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 5,
        max_chars: int = 4000,
    ) -> str:
        results = await self.retrieve(tenant_id=tenant_id, query=query, limit=limit)
        if not results:
            return ""

        lines = ["# Relevant context from Company Brain", ""]
        budget = max_chars - len("\n".join(lines))

        for result in results:
            entry = f"- ({result.score:.2f}) {result.record.content}"
            if len(entry) > budget:
                break
            lines.append(entry)
            budget -= len(entry) + 1

        rendered = "\n".join(lines)
        logger.info("context.built", tenant=tenant_id, records=len(results), chars=len(rendered))
        return rendered
