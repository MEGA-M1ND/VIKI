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


def get_tenant_id(request: Request) -> str:
    """Return tenant_id from header (via middleware state) or query param.

    Falls back to ``"default"`` if neither is provided. This dependency never
    raises — use :func:`require_tenant_id` for routes that mandate a tenant.

    Args:
        request: The incoming HTTP request.

    Returns:
        The tenant identifier string.
    """
    return (
        getattr(request.state, "tenant_id", None)
        or request.query_params.get("tenant_id")
        or "default"
    )


_TENANT_RE = __import__("re").compile(r"^[a-zA-Z0-9_-]{1,64}$")


def require_tenant_id(request: Request) -> str:
    """Return tenant_id from header or query param; raise 400 if absent.

    Also validates the format: only alphanumeric, underscore, and hyphen
    characters are accepted (1–64 chars).

    Args:
        request: The incoming HTTP request.

    Returns:
        The validated tenant identifier string.

    Raises:
        HTTPException: 400 if no tenant_id is provided or the format is invalid.
    """
    tid: str | None = (
        getattr(request.state, "tenant_id", None)
        or request.query_params.get("tenant_id")
    )
    if not tid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header or tenant_id query param required",
        )
    if not _TENANT_RE.match(tid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant_id format: must be 1–64 alphanumeric, underscore, or hyphen characters",
        )
    return tid
