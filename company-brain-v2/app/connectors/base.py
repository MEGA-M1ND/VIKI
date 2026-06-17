"""Connector interface.

A connector is the *only* component that talks to an external source system.
It knows how to authenticate and fetch, and it normalizes results into
:class:`~app.models.documents.RawDocument`. It must not perform extraction,
storage, or retrieval — those are downstream concerns.

Business logic for concrete connectors (Gmail, Notion, Slack) is intentionally
omitted in the MVP scaffold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.models.common import SourceType
from app.models.documents import RawDocument


class BaseConnector(ABC):
    """Abstract base for all source connectors."""

    #: The source system this connector serves. Concrete classes must set it.
    source: SourceType

    @abstractmethod
    def fetch(
        self,
        *,
        tenant_id: str,
        lookback_hours: int = 24,
    ) -> AsyncIterator[RawDocument]:
        """Yield normalized documents from the source.

        Args:
            tenant_id: Tenant the fetched documents belong to.
            lookback_hours: Only fetch items changed within this window.

        Yields:
            :class:`RawDocument` instances.

        Raises:
            ConnectorAuthError: Authentication failed.
            ConnectorRateLimitError: The source rate-limited the request.
            ConnectorError: Any other source failure.
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the connector can reach and authenticate to its source."""
        raise NotImplementedError
