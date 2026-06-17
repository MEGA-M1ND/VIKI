"""Domain models — the shared vocabulary of the system.

The pipeline flows: ``RawDocument`` -> ``ExtractedFact`` -> ``MemoryRecord``,
and retrieval returns ``RetrievalResult`` for a ``RetrievalQuery``.
"""

from app.models.common import (
    DomainModel,
    EntityType,
    FactType,
    SourceType,
)
from app.models.documents import RawDocument
from app.models.facts import EntityRef, ExtractedFact
from app.models.memory import MemoryRecord
from app.models.retrieval import RetrievalQuery, RetrievalResult

__all__ = [
    "DomainModel",
    "EntityRef",
    "EntityType",
    "ExtractedFact",
    "FactType",
    "MemoryRecord",
    "RawDocument",
    "RetrievalQuery",
    "RetrievalResult",
    "SourceType",
]
