from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator


@dataclass
class RawDocument:
    source: str
    source_id: str
    content: str
    metadata: dict = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    author: str | None = None
    subject: str | None = None


class BaseConnector(ABC):
    @abstractmethod
    async def fetch(self, lookback_hours: int = 24) -> AsyncIterator[RawDocument]:
        """Yield RawDocument objects from the source."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if the connector can reach its source."""
        ...
