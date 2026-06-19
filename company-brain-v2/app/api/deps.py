"""FastAPI dependency providers.

Collaborators are built once at startup and stored on ``app.state``; these
helpers expose them to route handlers via ``Depends`` and ``Request``.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.db.vc_repo import VCRepository
from app.llm.base import LLMProvider
from app.services.container import ServiceContainer
from app.services.health import HealthService


def get_container(request: Request) -> ServiceContainer:
    """Return the process-wide :class:`ServiceContainer`."""
    return request.app.state.container


def get_health_service(request: Request) -> HealthService:
    """Return a :class:`HealthService` bound to the current container."""
    return HealthService(get_container(request))


def get_llm_provider(request: Request) -> LLMProvider | None:
    """Return the configured LLM provider, or None if not wired."""
    return get_container(request).llm


def get_vc_repository(request: Request) -> VCRepository:
    """Return the wired VC repository.

    Raises:
        HTTPException: 503 if no repository is wired (should not happen — the
            in-memory default means it is always present).
    """
    repo = get_container(request).vc_repository
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VC repository is not available.",
        )
    return repo
