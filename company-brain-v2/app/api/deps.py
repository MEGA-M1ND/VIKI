"""FastAPI dependency providers.

Collaborators are built once at startup and stored on ``app.state``; these
helpers expose them to route handlers via ``Depends`` and ``Request``.
"""

from __future__ import annotations

from fastapi import Request

from app.services.container import ServiceContainer
from app.services.health import HealthService


def get_container(request: Request) -> ServiceContainer:
    """Return the process-wide :class:`ServiceContainer`."""
    return request.app.state.container


def get_health_service(request: Request) -> HealthService:
    """Return a :class:`HealthService` bound to the current container."""
    return HealthService(get_container(request))
