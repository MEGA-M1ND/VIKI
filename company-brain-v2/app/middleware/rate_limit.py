"""Per-tenant sliding-window rate limiter.

Uses an in-memory deque per (path_prefix, tenant_id) key. Replace with Redis
for multi-process deployments where the in-memory state would not be shared.

Default limits (requests per 60-second window):
    /ingest  — 100
    /ask     — 60
    /vc      — 120
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Default route-prefix limits: prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/ingest": (100, 60),
    "/ask": (60, 60),
    "/vc": (120, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed on (path_prefix, tenant_id).

    Args:
        app: The ASGI application to wrap.
        limits: Mapping of path prefix → (max_requests, window_seconds).
            Defaults to :data:`RATE_LIMITS`.
    """

    def __init__(
        self,
        app,
        limits: dict[str, tuple[int, int]] = RATE_LIMITS,
    ) -> None:
        super().__init__(app)
        self._limits = limits
        # (path_prefix, tenant_id) -> deque of monotonic timestamps
        self._windows: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Check rate limit for the current tenant and path prefix.

        Args:
            request: The incoming HTTP request.
            call_next: The next handler in the middleware chain.

        Returns:
            A 429 JSON response if the limit is exceeded, otherwise the
            response from the downstream handler.
        """
        tenant_id: str = (
            request.headers.get("X-Tenant-ID")
            or request.query_params.get("tenant_id")
            or "default"
        )
        path: str = request.url.path
        for prefix, (limit, window_s) in self._limits.items():
            if path.startswith(prefix):
                key = (prefix, tenant_id)
                now = time.monotonic()
                dq = self._windows[key]
                # Remove expired timestamps from the left
                while dq and dq[0] < now - window_s:
                    dq.popleft()
                if len(dq) >= limit:
                    retry_after = int(window_s - (now - dq[0])) + 1
                    return JSONResponse(
                        status_code=429,
                        content={"error": "Rate limit exceeded"},
                        headers={"Retry-After": str(retry_after)},
                    )
                dq.append(now)
                break
        return await call_next(request)
