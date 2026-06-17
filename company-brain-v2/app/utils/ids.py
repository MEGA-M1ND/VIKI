"""Identifier and time helpers shared across domain models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id(prefix: str = "") -> str:
    """Generate a unique, sortable-ish identifier.

    Args:
        prefix: Optional short prefix (e.g. ``"doc"``) for readability.

    Returns:
        A string id such as ``"doc_3f9a1c2e..."`` or a bare UUID hex.
    """
    raw = uuid.uuid4().hex
    return f"{prefix}_{raw}" if prefix else raw


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(tz=UTC)
