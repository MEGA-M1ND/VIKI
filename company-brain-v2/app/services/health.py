"""Health and readiness aggregation.

``liveness`` answers "is the process up?" (always cheap/true here).
``readiness`` answers "can we serve traffic?" by checking dependencies such as
the memory store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.container import ServiceContainer

logger = get_logger(__name__)


@dataclass(slots=True)
class ReadinessReport:
    """Outcome of a readiness probe.

    Attributes:
        ready: Overall readiness (``True`` only if every check passed).
        checks: Per-dependency results keyed by name.
    """

    ready: bool
    checks: dict[str, bool] = field(default_factory=dict)


class HealthService:
    """Computes liveness and readiness for the API."""

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container

    @staticmethod
    def liveness() -> bool:
        """Return ``True`` — the process is alive if this executes."""
        return True

    async def readiness(self) -> ReadinessReport:
        """Probe dependencies and aggregate the result."""
        checks: dict[str, bool] = {}

        try:
            checks["memory_store"] = await self._container.memory_store.health_check()
        except Exception as exc:  # noqa: BLE001 - probe must not raise
            logger.warning("health.memory_check_failed", error=str(exc))
            checks["memory_store"] = False

        ready = all(checks.values())
        return ReadinessReport(ready=ready, checks=checks)
