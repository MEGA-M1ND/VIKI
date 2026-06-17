"""API request/response schemas.

Kept distinct from domain models so the public HTTP contract can evolve
independently of internal types.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str
    service: str
    env: str


class ReadinessResponse(BaseModel):
    """Readiness response with per-dependency detail."""

    ready: bool
    checks: dict[str, bool]
