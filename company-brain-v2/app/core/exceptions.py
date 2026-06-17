"""Base exception hierarchy for Company Brain.

All domain errors derive from :class:`CompanyBrainError` so callers can catch
the whole family with one ``except`` and the API layer can map them to HTTP
responses in a single place.

Hierarchy::

    CompanyBrainError
    ├── ConfigurationError
    ├── ConnectorError
    │   ├── ConnectorAuthError
    │   └── ConnectorRateLimitError
    ├── IngestionError
    ├── ExtractionError
    ├── MemoryError
    │   ├── MemoryWriteError
    │   └── MemoryQueryError
    ├── ContextError
    └── NotFoundError
"""

from __future__ import annotations


class CompanyBrainError(Exception):
    """Root of all application errors.

    Args:
        message: Human-readable description.
        details: Optional structured context for logging/debugging.
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = details or {}

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.details:
            return f"{self.message} | details={self.details}"
        return self.message


class ConfigurationError(CompanyBrainError):
    """Invalid or missing configuration."""


# --- Connectors --------------------------------------------------------------


class ConnectorError(CompanyBrainError):
    """A connector failed to reach or read from its source."""


class ConnectorAuthError(ConnectorError):
    """Authentication/authorization with the source failed."""


class ConnectorRateLimitError(ConnectorError):
    """The source rejected a request due to rate limiting."""


class ConnectorSyncError(ConnectorError):
    """A sync run across multiple documents partially or fully failed.

    ``details`` typically includes ``fetched``, ``failed``, and ``errors`` keys.
    """


# --- Pipeline stages ---------------------------------------------------------


class IngestionError(CompanyBrainError):
    """A document could not be ingested."""


class ExtractionError(CompanyBrainError):
    """Fact extraction failed for a document."""


# --- Memory ------------------------------------------------------------------


class MemoryError(CompanyBrainError):
    """Generic memory-store failure."""


class MemoryWriteError(MemoryError):
    """Writing a record to the memory store failed."""


class WriteFailureError(MemoryWriteError):
    """A fact could not be written and was routed to the dead-letter queue.

    ``details`` typically includes ``fact_id`` and ``destination`` (path of the
    dead-letter file).
    """


class MemoryQueryError(MemoryError):
    """Querying the memory store failed."""


# --- Misc --------------------------------------------------------------------


class ContextError(CompanyBrainError):
    """Building or injecting agent context failed."""


class NotFoundError(CompanyBrainError):
    """A requested resource does not exist."""
