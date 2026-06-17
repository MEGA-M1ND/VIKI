"""Context injection interface.

The context layer is the read-side counterpart to ingestion: given a query and
a tenant, it retrieves relevant memory and formats it for consumption by a
downstream agent (e.g. as a system-prompt preamble). Keeping it behind an
interface lets us vary formatting/budgeting strategy independently of storage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.retrieval import RetrievalResult


class ContextProvider(ABC):
    """Abstract base for context providers."""

    @abstractmethod
    async def build_context(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 5,
        max_chars: int = 4000,
    ) -> str:
        """Retrieve relevant memory and render it as an injectable string.

        Args:
            tenant_id: Tenant whose memory to search.
            query: The agent's current task/query.
            limit: Max number of memory records to include.
            max_chars: Soft budget for the rendered context length.

        Returns:
            A formatted context block (empty string if nothing relevant).

        Raises:
            ContextError: Building context failed.
        """
        raise NotImplementedError

    @abstractmethod
    async def retrieve(
        self,
        *,
        tenant_id: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievalResult]:
        """Return the raw ranked results behind :meth:`build_context`."""
        raise NotImplementedError
