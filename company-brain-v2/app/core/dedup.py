"""Source-level deduplication for retrieval results.

Prevents a single email or document from dominating the result set
by keeping only the top-scoring N facts per source document.
"""
from __future__ import annotations

from collections import defaultdict

from app.models.retrieval import ScoredFact


def deduplicate_by_source(
    facts: list[ScoredFact],
    max_per_source: int = 2,
) -> list[ScoredFact]:
    """For each unique source_doc_id, keep only the top-scoring max_per_source facts.

    Facts with no source_doc_id are treated as belonging to unique sources
    (each has its own implicit bucket) and are always kept.

    Preserves ranking order. Facts without a source_doc_id are always kept.

    Args:
        facts: Scored facts in descending score order.
        max_per_source: Maximum facts to keep per source document.

    Returns:
        Deduplicated list in the same relative order.
    """
    seen: defaultdict[str, int] = defaultdict(int)
    result: list[ScoredFact] = []
    no_source_counter = 0

    for fact in facts:
        if fact.source_doc_id is None:
            # no source ID — treat as unique, always include
            key = f"__no_source_{no_source_counter}__"
            no_source_counter += 1
        else:
            key = fact.source_doc_id

        if seen[key] < max_per_source:
            seen[key] += 1
            result.append(fact)

    return result
