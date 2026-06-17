"""Extraction node.

Calls the LLM extractor prompt and converts the JSON response into a list of
:class:`~app.models.facts.ExtractedFact` objects.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.exceptions import ExtractionError
from app.core.logging import get_logger
from app.graphs.state import PipelineState
from app.llm.base import LLMProvider
from app.models.facts import EntityRef, ExtractedFact
from app.prompts.extraction import build_extract_messages

logger = get_logger(__name__)

_MAX_FACTS = 10
_MAX_ENTITIES = 10


def make_extract_node(llm: LLMProvider) -> Callable[[PipelineState], Awaitable[Any]]:
    """Return an async extract node bound to *llm*."""

    async def extract_node(state: PipelineState) -> dict:
        doc = state["document"]
        messages = build_extract_messages(
            source=str(doc.source),
            title=doc.title or "",
            author=doc.author or "",
            content=doc.content,
        )
        try:
            raw = await llm.chat(messages, json_mode=True)
            parsed = json.loads(raw)
        except Exception as exc:
            logger.error("extract.llm_failed", doc_id=doc.id, error=str(exc))
            raise ExtractionError("LLM extraction failed", details={"doc_id": doc.id, "error": str(exc)}) from exc

        raw_facts = parsed.get("facts", [])[:_MAX_FACTS]
        raw_entities = parsed.get("entities", [])[:_MAX_ENTITIES]

        global_entities = [
            EntityRef(name=e["name"], type=e.get("type", "other"))
            for e in raw_entities
            if e.get("name")
        ]

        facts: list[ExtractedFact] = []
        for rf in raw_facts:
            if not rf.get("statement"):
                continue
            fact = ExtractedFact(
                document_id=doc.id,
                tenant_id=doc.tenant_id,
                source=doc.source,
                statement=rf["statement"],
                subject=rf.get("subject"),
                predicate=rf.get("predicate"),
                object_=rf.get("object"),
                tags=rf.get("tags", []),
                fact_type=rf.get("fact_type", "fact"),
                confidence=float(rf.get("confidence", 1.0)),
                entities=global_entities,
            )
            facts.append(fact)

        logger.info("extract.done", doc_id=doc.id, facts=len(facts))
        return {**state, "facts": facts}

    return extract_node
