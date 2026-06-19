"""Initial schema: memory_records table with pgvector.

Revision ID: 001
Revises:
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    """Create memory_records table with pgvector extension and indexes."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_records",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("record_type", sa.String, nullable=False, server_default="fact"),
        sa.Column("source", sa.String, nullable=True),
        sa.Column("source_doc_id", sa.String, nullable=True),
        sa.Column("source_refs", JSONB, nullable=False, server_default="[]"),
        sa.Column("source_type_hint", sa.String, nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("record_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("memory_records_tenant_idx", "memory_records", ["tenant_id"])
    op.create_index("memory_records_source_doc_idx", "memory_records", ["source_doc_id"])
    op.create_index(
        "memory_records_tenant_created_idx", "memory_records", ["tenant_id", "created_at"]
    )
    # ivfflat index for cosine similarity (requires data to set lists; 100 is a safe default)
    op.execute(
        "CREATE INDEX memory_records_embedding_idx ON memory_records "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    """Drop memory_records table and its indexes."""
    op.execute("DROP INDEX IF EXISTS memory_records_embedding_idx")
    op.drop_index("memory_records_tenant_created_idx", "memory_records")
    op.drop_index("memory_records_source_doc_idx", "memory_records")
    op.drop_index("memory_records_tenant_idx", "memory_records")
    op.drop_table("memory_records")
