"""LLM-backed fact extractor."""

from __future__ import annotations

import json

from app.core.exceptions import ExtractionError
from app.core.logging import get_logger
from app.ingestion.base import BaseExtractor
from app.llm.base import LLMProvider
from app.models.common import EntityType
from app.models.documents import RawDocument
from app.models.facts import EntityRef, ExtractedFact
from app.prompts.extraction import build_extract_messages

_ENTITY_TYPE_VALUES = {e.value for e in EntityType}

logger = get_logger(__name__)

_MAX_FACTS = 10
_MAX_ENTITIES = 10


class LLMExtractor(BaseExtractor):
    """Extracts durable facts from documents using an LLM."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def extract(self, document: RawDocument) -> list[ExtractedFact]:
        messages = build_extract_messages(
            source=str(document.source),
            title=document.title or "",
            author=document.author or "",
            content=document.content,
        )
        try:
            raw = await self._llm.chat(messages, json_mode=True)
            parsed = json.loads(raw)
        except Exception as exc:
            raise ExtractionError(
                "LLM extraction failed",
                details={"doc_id": document.id, "error": str(exc)},
            ) from exc

        raw_facts = parsed.get("facts", [])[:_MAX_FACTS]
        raw_entities = parsed.get("entities", [])[:_MAX_ENTITIES]

        global_entities = [
            EntityRef(
                name=e["name"],
                type=e.get("type", "other") if e.get("type") in _ENTITY_TYPE_VALUES else "other",
            )
            for e in raw_entities
            if e.get("name")
        ]

        facts: list[ExtractedFact] = []
        for rf in raw_facts:
            if not rf.get("statement"):
                continue
            facts.append(
                ExtractedFact(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    source=document.source,
                    statement=rf["statement"],
                    subject=rf.get("subject"),
                    predicate=rf.get("predicate"),
                    object_=rf.get("object"),
                    tags=rf.get("tags", []),
                    fact_type=rf.get("fact_type", "fact"),
                    confidence=float(rf.get("confidence", 1.0)),
                    entities=global_entities,
                )
            )

        logger.info("llm_extractor.done", doc_id=document.id, facts=len(facts))
        return facts
