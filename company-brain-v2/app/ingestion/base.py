"""Extraction interface.

Extraction is the stage that turns a :class:`~app.models.documents.RawDocument`
into durable :class:`~app.models.facts.ExtractedFact` objects. It is kept
separate from connectors (which only fetch) and from memory (which only
stores), so the extraction strategy — LLM prompt, rules, hybrid — can evolve
independently.

LLM prompt logic is intentionally omitted in the MVP scaffold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.documents import RawDocument
from app.models.facts import ExtractedFact


class BaseExtractor(ABC):
    """Abstract base for fact extractors."""

    @abstractmethod
    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        """Extract zero or more durable facts from a document.

        Args:
            document: The document to analyze.

        Returns:
            A list of extracted facts (possibly empty if nothing is worth
            remembering).

        Raises:
            ExtractionError: Extraction failed irrecoverably.
        """
        raise NotImplementedError
