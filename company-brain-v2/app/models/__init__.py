"""Domain models — the shared vocabulary of the system.

The pipeline flows: ``RawDocument`` -> ``ExtractedFact`` -> ``MemoryRecord``,
and retrieval returns ``RetrievalResult`` for a ``RetrievalQuery``.
"""

from app.models.common import (
    DomainModel,
    EntityType,
    FactType,
    SourceType,
    ValidityKind,
)
from app.models.documents import RawDocument
from app.models.facts import EntityRef, ExtractedFact
from app.models.memory import MemoryRecord
from app.models.results import Err, Ok
from app.models.retrieval import RetrievalQuery, RetrievalResult

__all__ = [
    "DomainModel",
    "EntityRef",
    "EntityType",
    "Err",
    "ExtractedFact",
    "FactType",
    "MemoryRecord",
    "Ok",
    "RawDocument",
    "RetrievalQuery",
    "RetrievalResult",
    "SourceType",
    "ValidityKind",
]
