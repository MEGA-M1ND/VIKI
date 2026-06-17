"""Retrieval service.

A thin facade over the memory store that adds tenant scoping, result capping,
and timing logs. API routes and the context graph both consume this service
rather than calling the store directly.
"""

from __future__ import annotations

import time

from app.core.logging import get_logger
from app.memory.base import MemoryStore
from app.models.retrieval import RetrievalQuery, RetrievalResult

logger = get_logger(__name__)


class RetrievalService:
    """Retrieves ranked memory records for a query.

    Args:
        store: Memory backend to query.
        default_limit: Max results when the caller does not specify.
        max_limit: Hard cap on the number of results returned.
    """

    def __init__(
        self,
        store: MemoryStore,
        default_limit: int = 5,
        max_limit: int = 50,
    ) -> None:
        self._store = store
        self._default_limit = default_limit
        self._max_limit = max_limit

    async def query(
        self,
        *,
        tenant_id: str,
        text: str,
        limit: int | None = None,
        filters: dict[str, object] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant records for *text* in *tenant_id*.

        Args:
            tenant_id: Tenant whose memory to search.
            text: Natural-language query.
            limit: Max results (capped at :attr:`max_limit`).
            filters: Optional metadata equality filters.

        Returns:
            Ranked results, best first.
        """
        effective_limit = min(limit or self._default_limit, self._max_limit)
        q = RetrievalQuery(
            tenant_id=tenant_id,
            text=text,
            limit=effective_limit,
            filters=filters or {},
        )

        t0 = time.monotonic()
        results = await self._store.query(q)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "retrieval.done",
            tenant_id=tenant_id,
            hits=len(results),
            elapsed_ms=elapsed_ms,
        )
        return results
