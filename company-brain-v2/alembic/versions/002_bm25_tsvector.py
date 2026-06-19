"""Add BM25 tsvector column and GIN index to memory_records.

Revision ID: 002
Revises: 001
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a GENERATED ALWAYS tsvector column over the content field for BM25 full-text search."""
    op.execute("""
        ALTER TABLE memory_records
        ADD COLUMN IF NOT EXISTS ts_content tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS memory_records_ts_idx "
        "ON memory_records USING GIN (ts_content)"
    )


def downgrade() -> None:
    """Remove tsvector column and its GIN index."""
    op.execute("DROP INDEX IF EXISTS memory_records_ts_idx")
    op.execute("ALTER TABLE memory_records DROP COLUMN IF EXISTS ts_content")
