"""Connector interface.

A connector is the *only* component that talks to an external source system.
It knows how to authenticate and fetch, and it normalizes results into
:class:`~app.models.documents.RawDocument`. It must not perform extraction,
storage, or retrieval — those are downstream concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from app.models.common import SourceType
from app.models.documents import RawDocument


class BaseConnector(ABC):
    """Abstract base for all source connectors."""

    #: The source system this connector serves. Concrete classes must set it.
    source: SourceType

    @abstractmethod
    async def authenticate(self) -> None:
        """Establish (or refresh) credentials for the source.

        Called once before the first ``fetch_documents`` call. Implementations
        should be idempotent — calling when already authenticated is a no-op.

        Raises:
            ConnectorAuthError: Authentication failed.
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_documents(
        self,
        *,
        tenant_id: str,
        since: datetime | None = None,
        lookback_hours: int = 24,
    ) -> AsyncIterator[RawDocument]:
        """Yield normalized documents from the source.

        Implementations must be declared as async generators (``async def ...
        yield``). Calling this method returns the iterator directly — no
        ``await`` required.

        Args:
            tenant_id: Tenant the fetched documents belong to.
            since: Fetch documents modified after this timestamp. If ``None``,
                falls back to ``lookback_hours`` relative to now.
            lookback_hours: Window in hours used when *since* is not given.

        Yields:
            :class:`RawDocument` instances.

        Raises:
            ConnectorAuthError: Authentication failed.
            ConnectorRateLimitError: The source rate-limited the request.
            ConnectorSyncError: Multiple documents could not be fetched.
            ConnectorError: Any other source failure.
        """
        raise NotImplementedError
        yield  # makes the abstract method an async generator; never reached

    def fetch(
        self,
        *,
        tenant_id: str,
        lookback_hours: int = 24,
    ) -> AsyncIterator[RawDocument]:
        """Convenience wrapper — delegates to :meth:`fetch_documents`."""
        return self.fetch_documents(tenant_id=tenant_id, lookback_hours=lookback_hours)

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the connector can reach and authenticate to its source."""
        raise NotImplementedError
