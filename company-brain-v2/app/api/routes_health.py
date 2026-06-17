"""Health and readiness endpoints.

- ``GET /health`` — liveness; cheap, never touches dependencies.
- ``GET /ready``  — readiness; probes dependencies, returns 503 if not ready.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_container, get_health_service
from app.api.schemas import HealthResponse, ReadinessResponse
from app.services.container import ServiceContainer
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    container: ServiceContainer = Depends(get_container),
) -> HealthResponse:
    """Liveness probe."""
    settings = container.settings
    return HealthResponse(status="ok", service=settings.app_name, env=settings.app_env)


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    response: Response,
    health_service: HealthService = Depends(get_health_service),
) -> ReadinessResponse:
    """Readiness probe.

    Returns HTTP 200 when all dependencies are healthy, otherwise 503.
    """
    report = await health_service.readiness()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=report.ready, checks=report.checks)
