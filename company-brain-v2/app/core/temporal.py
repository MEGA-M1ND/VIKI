"""Temporal query parsing.

Detects natural-language time references in a query string, returns a
cleaned query (with the temporal phrase removed) and an optional
after_date cutoff for filtering retrieval results by created_at.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

# Ordered longest-match-first so "last week" beats "week".
TEMPORAL_PATTERNS: list[tuple[str, timedelta]] = [
    ("this month", timedelta(days=30)),
    ("last month", timedelta(days=30)),
    ("this year", timedelta(days=365)),
    ("last year", timedelta(days=365)),
    ("this week", timedelta(days=7)),
    ("last week", timedelta(days=7)),
    ("yesterday", timedelta(days=1)),
    ("recently", timedelta(days=14)),
    ("lately", timedelta(days=30)),
    ("recent", timedelta(days=14)),
]


def extract_temporal_constraint(query: str) -> tuple[str, datetime | None]:
    """Detect temporal keywords and return a cleaned query + after_date.

    Matches are case-insensitive. The first matching pattern wins.
    Matched text is removed from the returned query (leading/trailing
    whitespace and duplicate spaces are collapsed).

    Args:
        query: The raw natural-language query.

    Returns:
        (cleaned_query, after_date) where after_date is None if no
        temporal keyword was found. after_date is timezone-aware UTC.

    Examples:
        >>> extract_temporal_constraint("what companies approached me lately")
        ("what companies approached me", datetime(...))
        >>> extract_temporal_constraint("tell me about Alice")
        ("tell me about Alice", None)
    """
    now = datetime.now(tz=UTC)

    for phrase, delta in TEMPORAL_PATTERNS:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(query):
            cleaned = pattern.sub("", query)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            after_date = now - delta
            return cleaned, after_date

    return query, None
