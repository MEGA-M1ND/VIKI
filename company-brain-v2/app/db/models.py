"""SQLAlchemy ORM models for the pgvector memory backend and VC layer.

Memory: memory_records stores MemoryRecord data including the embedding
vector (for semantic search) and a tsvector column (for BM25).

VC (Phase 2): founders, deal_opportunities, and fund_signals back the VC
Intelligence Layer. These are additive — they share the same declarative
``Base`` but are otherwise independent of the memory pipeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
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


class FounderRow(Base):
    """ORM row for founders table (VC layer)."""

    __tablename__ = "founders"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    last_contact_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_signals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("founders_tenant_contact_idx", "tenant_id", "last_contact_date"),
    )


class DealOpportunityRow(Base):
    """ORM row for deal_opportunities table (VC layer)."""

    __tablename__ = "deal_opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    founder_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("founders.id"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    deal_stage: Mapped[str] = mapped_column(String, nullable=False)
    raise_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_activity_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_doc_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("deal_opportunities_tenant_activity_idx", "tenant_id", "last_activity_date"),
    )


class FundSignalRow(Base):
    """ORM row for fund_signals table (VC layer)."""

    __tablename__ = "fund_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("founders.id"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    signal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("fund_signals_tenant_date_idx", "tenant_id", "signal_date"),
    )
