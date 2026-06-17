"""Classification node.

Asks the LLM whether the document is worth extracting from. A low-confidence
or negative response short-circuits the pipeline before any expensive extraction.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.graphs.state import PipelineState
from app.llm.base import LLMProvider
from app.prompts.classification import build_classify_messages

logger = get_logger(__name__)

_CONFIDENCE_THRESHOLD = 0.5


def make_classify_node(
    llm: LLMProvider, threshold: float = _CONFIDENCE_THRESHOLD
) -> Callable[[PipelineState], Awaitable[Any]]:
    """Return an async classify node bound to *llm*."""

    async def classify_node(state: PipelineState) -> dict:
        doc = state["document"]
        messages = build_classify_messages(
            source=str(doc.source),
            title=doc.title or "",
            author=doc.author or "",
            content=doc.content,
        )
        try:
            raw = await llm.chat(messages, json_mode=True)
            parsed = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("classify.parse_failed", doc_id=doc.id, error=str(exc))
            # Default to ingesting on parse failure — don't silently drop docs
            return {
                **state,
                "is_worth_remembering": True,
                "confidence": 0.5,
                "classifier_reasoning": f"parse_error: {exc}",
            }

        worth = bool(parsed.get("is_worth_remembering", True))
        confidence = float(parsed.get("confidence", 1.0))
        reasoning = str(parsed.get("reasoning", ""))

        if worth and confidence < threshold:
            worth = False
            reasoning = f"confidence {confidence:.2f} below threshold {threshold}"

        logger.info(
            "classify.result",
            doc_id=doc.id,
            worth=worth,
            confidence=confidence,
        )
        return {
            **state,
            "is_worth_remembering": worth,
            "confidence": confidence,
            "classifier_reasoning": reasoning,
        }

    return classify_node
