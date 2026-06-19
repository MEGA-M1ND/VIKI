"""Tests for temporal query parsing."""
from __future__ import annotations

from datetime import UTC, datetime

from app.core.temporal import extract_temporal_constraint


def test_lately_removes_phrase() -> None:
    """'lately' should be removed from the query and return ~30 day cutoff."""
    cleaned, after = extract_temporal_constraint("what companies approached me lately")
    assert "lately" not in cleaned
    assert after is not None
    assert "what companies approached me" in cleaned


def test_recently_14_days() -> None:
    """'recently' should return a ~14-day cutoff."""
    cleaned, after = extract_temporal_constraint("who contacted me recently")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 13 <= delta.days <= 15  # ~14 days


def test_last_week_7_days() -> None:
    """'last week' should return a ~7-day cutoff."""
    cleaned, after = extract_temporal_constraint("emails from last week")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 6 <= delta.days <= 8


def test_this_week() -> None:
    """'this week' should return a ~7-day cutoff."""
    cleaned, after = extract_temporal_constraint("meetings this week")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 6 <= delta.days <= 8


def test_yesterday_1_day() -> None:
    """'yesterday' should return a ~1-day cutoff."""
    cleaned, after = extract_temporal_constraint("what happened yesterday")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 0 <= delta.days <= 2


def test_last_month_30_days() -> None:
    """'last month' should return a ~30-day cutoff."""
    cleaned, after = extract_temporal_constraint("meetings last month")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 29 <= delta.days <= 31


def test_this_month() -> None:
    """'this month' should return a ~30-day cutoff."""
    cleaned, after = extract_temporal_constraint("emails this month")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 29 <= delta.days <= 31


def test_last_year_365_days() -> None:
    """'last year' should return a ~365-day cutoff."""
    cleaned, after = extract_temporal_constraint("investments last year")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 364 <= delta.days <= 366


def test_no_temporal_keyword_returns_none() -> None:
    """Queries without temporal keywords should return None for after_date."""
    cleaned, after = extract_temporal_constraint("tell me about Alice from Acme")
    assert cleaned == "tell me about Alice from Acme"
    assert after is None


def test_empty_query() -> None:
    """Empty string should return empty cleaned query and no cutoff."""
    cleaned, after = extract_temporal_constraint("")
    assert cleaned == ""
    assert after is None


def test_case_insensitive() -> None:
    """Temporal phrases should be matched case-insensitively."""
    cleaned, after = extract_temporal_constraint("what happened LATELY")
    assert after is not None
    assert "LATELY" not in cleaned


def test_cleaned_query_stripped() -> None:
    """A query of only a temporal phrase should clean to empty string."""
    cleaned, after = extract_temporal_constraint("lately")
    assert cleaned == ""
    assert after is not None


def test_phrase_removed_mid_sentence() -> None:
    """Temporal phrase mid-sentence should be removed cleanly."""
    cleaned, after = extract_temporal_constraint("jobs I applied for last week in Berlin")
    assert "last week" not in cleaned
    assert after is not None
    assert "jobs I applied for" in cleaned


def test_after_date_is_utc() -> None:
    """Returned after_date should be timezone-aware UTC."""
    _, after = extract_temporal_constraint("meetings recently")
    assert after is not None
    assert after.tzinfo is not None


def test_this_year() -> None:
    """'this year' should return a ~365-day cutoff."""
    cleaned, after = extract_temporal_constraint("what happened this year")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 364 <= delta.days <= 366


def test_recent_14_days() -> None:
    """'recent' (without 'ly') should return a ~14-day cutoff."""
    cleaned, after = extract_temporal_constraint("show recent activity")
    assert after is not None
    delta = datetime.now(tz=UTC) - after
    assert 13 <= delta.days <= 15
