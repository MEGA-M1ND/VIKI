"""Structured logging setup built on :mod:`structlog`.

Call :func:`configure_logging` once at startup. Everywhere else, obtain a
logger with :func:`get_logger` and log with key/value pairs::

    log = get_logger(__name__)
    log.info("document.ingested", source="gmail", doc_id=doc.id)
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, level: str = "INFO", json_logs: bool = False) -> None:
    """Configure stdlib logging and structlog processors.

    Args:
        level: Root log level name (e.g. ``"INFO"``).
        json_logs: When ``True``, render logs as JSON (suited to production
            log aggregation); otherwise use a colorized console renderer.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    Args:
        name: Optional logger name (typically ``__name__``).
    """
    return structlog.get_logger(name)
