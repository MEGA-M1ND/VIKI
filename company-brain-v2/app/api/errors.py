"""Maps domain exceptions to HTTP responses in one place."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    CompanyBrainError,
    ConfigurationError,
    ConnectorAuthError,
    ConnectorRateLimitError,
    NotFoundError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Domain error type -> HTTP status code. Unlisted errors fall back to 500.
_STATUS_MAP: dict[type[CompanyBrainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ConnectorAuthError: status.HTTP_502_BAD_GATEWAY,
    ConnectorRateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the domain exception handler to the app."""

    @app.exception_handler(CompanyBrainError)
    async def _handle_domain_error(request: Request, exc: CompanyBrainError) -> JSONResponse:
        code = _STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.error(
            "api.domain_error",
            path=request.url.path,
            error_type=type(exc).__name__,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=code,
            content={"error": type(exc).__name__, "message": exc.message, "details": exc.details},
        )
