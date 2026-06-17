"""HTTP API layer (FastAPI routers, schemas, dependencies)."""

from app.api.routes_health import router as health_router

__all__ = ["health_router"]
