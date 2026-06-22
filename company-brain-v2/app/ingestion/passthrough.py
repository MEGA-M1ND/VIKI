"""Passthrough extractor — no LLM required.

Creates one :class:`~app.models.facts.ExtractedFact` per document using the
document's title and content directly. Useful for local dev and smoke tests.
"""

from __future__ import annotations

from app.ingestion.base import BaseExtractor
from app.models.documents import RawDocument
from app.models.facts import ExtractedFact


class PassthroughExtractor(BaseExtractor):
    """Stores document content as-is — no classification, no LLM call."""

    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        statement = document.content[:500].strip()
        if not statement:
            return []
        return [
            ExtractedFact(
                document_id=document.id,
                tenant_id=document.tenant_id,
                source=document.source,
                statement=statement,
            )
        ]
