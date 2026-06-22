"""Query rewriting for short/entity queries.

For queries with four or fewer tokens, uses the LLM to generate search-optimised
variants so hybrid retrieval finds contextually relevant records even when the
original query is ambiguous or terse (e.g. "Accenture Interview").

Always returns at least ``[original_query]`` — never raises, never blocks the
request if the LLM is slow or unavailable.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm.base import LLMProvider

logger = get_logger(__name__)

_REWRITE_SYSTEM = (
    "You expand a short search query into three search-optimised variants. "
    "Return ONLY three lines, one variant per line, no bullets, no numbering, no explanation. "
    "Variants should be richer and more specific — imagine the full email or note the user might be looking for."
)
_REWRITE_USER = "Query: {query}"

# Rewrite only queries short enough to be ambiguous
_MAX_TOKENS_TO_REWRITE = 4


async def rewrite_query(query: str, llm: LLMProvider) -> list[str]:
    """Return the original query plus up to three LLM-generated variants.

    Skips the LLM for queries with more than ``_MAX_TOKENS_TO_REWRITE``
    whitespace-delimited tokens — those already have enough retrieval signal.

    Args:
        query: Original (possibly temporal-stripped) user query.
        llm: Configured LLM provider.

    Returns:
        List starting with ``query``, followed by up to three variants.
        Falls back to ``[query]`` on any error or when no variants are produced.
    """
    tokens = query.split()
    if len(tokens) > _MAX_TOKENS_TO_REWRITE:
        return [query]

    try:
        raw = await llm.chat(
            [
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": _REWRITE_USER.format(query=query)},
            ],
            temperature=0.3,
        )
        variants = [line.strip() for line in raw.strip().splitlines() if line.strip()][:3]
        if variants:
            logger.debug("query_rewriter.expanded", original=query, variants=variants)
            return [query] + variants
    except Exception:
        logger.debug("query_rewriter.llm_error", query=query, exc_info=True)

    return [query]
