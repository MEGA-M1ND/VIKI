"""Middleware package for the Company Brain API.

Contains :class:`~app.middleware.tenant.TenantMiddleware` for reading
the X-Tenant-ID header and :class:`~app.middleware.rate_limit.RateLimitMiddleware`
for per-tenant sliding-window rate limiting.
"""
