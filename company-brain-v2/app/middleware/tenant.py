"""Tenant identification middleware.

Reads the X-Tenant-ID header and stores it on request.state so route
handlers and dependencies can retrieve it without parsing headers directly.
Does NOT enforce the header — enforcement is handled by the require_tenant_id
dependency for routes that need it.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TENANT_HEADER = "X-Tenant-ID"


class TenantMiddleware(BaseHTTPMiddleware):
    """Read X-Tenant-ID header and set request.state.tenant_id.

    This middleware is purely a reader/setter — it never returns 400. Routes
    that require a tenant use the :func:`~app.api.deps.require_tenant_id`
    dependency instead.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Extract tenant_id from header and attach to request state.

        Args:
            request: The incoming HTTP request.
            call_next: The next handler in the middleware chain.

        Returns:
            The response from the downstream handler.
        """
        tenant_id: str | None = request.headers.get(TENANT_HEADER)
        request.state.tenant_id = tenant_id
        return await call_next(request)
