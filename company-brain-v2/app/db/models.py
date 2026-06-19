"""SQLAlchemy ORM models for the pgvector memory backend.

One table: memory_records. Stores MemoryRecord data including the
embedding vector (for semantic search) and a tsvector column (for BM25).
"""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


EMBEDDING_DIM = 1536  # text-embedding-3-small dimensions


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class MemoryRecordRow(Base):
    """ORM row for memory_records table."""

    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    record_type: Mapped[str] = mapped_column(String, nullable=False, default="fact")
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    source_doc_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_type_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    record_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("memory_records_tenant_created_idx", "tenant_id", "created_at"),
        # GIN index for tsvector BM25 (column added in migration 002)
        # ivfflat index for vector cosine search (added in migration 001)
    )
