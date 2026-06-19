"""Source-type scoring weights for retrieval.

Applied after reranking to down-weight low-signal source types
(newsletters, digests) relative to direct outreach.
"""
from __future__ import annotations

SOURCE_TYPE_WEIGHTS: dict[str, float] = {
    "gmail_direct_outreach": 1.0,
    "gmail_reply_thread": 0.9,
    "notion_page": 0.85,
    "gmail_newsletter": 0.3,
    "gmail_digest": 0.25,
    "gmail_promotional": 0.1,
}

_DEFAULT_WEIGHT = 0.8  # unknown source types get a moderate penalty


def apply_source_weight(score: float, source_type_hint: str | None) -> float:
    """Multiply *score* by the weight for *source_type_hint*.

    Args:
        score: The pre-weight relevance score.
        source_type_hint: A string key from SOURCE_TYPE_WEIGHTS, or None.

    Returns:
        score * weight where weight comes from SOURCE_TYPE_WEIGHTS
        or _DEFAULT_WEIGHT if the hint is unknown.
    """
    weight = SOURCE_TYPE_WEIGHTS.get(source_type_hint or "", _DEFAULT_WEIGHT)
    return score * weight
