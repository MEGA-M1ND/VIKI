"""Async SQLAlchemy engine and session factory for the pgvector backend.

Engine is created once at module import via get_engine(). Session is
created per-request via get_session().
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_engine(dsn: str):
    """Create and cache an async SQLAlchemy engine for *dsn*.

    Args:
        dsn: asyncpg-compatible PostgreSQL DSN.

    Returns:
        A cached AsyncEngine instance.
    """
    engine = create_async_engine(
        dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )
    logger.info("db.engine.created", dsn=dsn.split("@")[-1])  # log host, not creds
    return engine


def get_session_factory(dsn: str) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to *dsn*.

    Args:
        dsn: asyncpg-compatible PostgreSQL DSN.

    Returns:
        An async_sessionmaker that produces AsyncSession instances.
    """
    engine = get_engine(dsn)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope(dsn: str) -> AsyncIterator[AsyncSession]:
    """Context manager that yields a session and commits/rolls back.

    Args:
        dsn: asyncpg-compatible PostgreSQL DSN.

    Yields:
        An AsyncSession that is committed on success or rolled back on error.
    """
    factory = get_session_factory(dsn)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
