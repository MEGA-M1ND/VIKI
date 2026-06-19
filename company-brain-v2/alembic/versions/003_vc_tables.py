"""VC intelligence tables: founders, deal_opportunities, fund_signals.

Revision ID: 003
Revises: 002
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the three VC tables, their FKs, and composite indexes."""
    # gen_random_uuid() needs pgcrypto on PG<13; harmless/idempotent on PG16.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "founders",
        sa.Column(
            "id",
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("company_name", sa.String, nullable=False),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("domain", sa.String, nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("last_contact_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("raw_signals", JSONB, nullable=False, server_default="[]"),
        sa.Column("source_doc_ids", JSONB, nullable=False, server_default="[]"),
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
    op.create_index("founders_tenant_idx", "founders", ["tenant_id"])
    op.create_index(
        "founders_tenant_contact_idx", "founders", ["tenant_id", "last_contact_date"]
    )

    op.create_table(
        "deal_opportunities",
        sa.Column(
            "id",
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column(
            "founder_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("founders.id"),
            nullable=False,
        ),
        sa.Column("company_name", sa.String, nullable=False),
        sa.Column("deal_stage", sa.String, nullable=False),
        sa.Column("raise_amount_usd", sa.Float, nullable=True),
        sa.Column("last_activity_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_action", sa.Text, nullable=True),
        sa.Column("source_doc_ids", JSONB, nullable=False, server_default="[]"),
    )
    op.create_index(
        "deal_opportunities_tenant_idx", "deal_opportunities", ["tenant_id"]
    )
    op.create_index(
        "deal_opportunities_tenant_activity_idx",
        "deal_opportunities",
        ["tenant_id", "last_activity_date"],
    )

    op.create_table(
        "fund_signals",
        sa.Column(
            "id",
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("signal_type", sa.String, nullable=False),
        sa.Column(
            "founder_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("founders.id"),
            nullable=True,
        ),
        sa.Column("company_name", sa.String, nullable=False),
        sa.Column("signal_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
    )
    op.create_index("fund_signals_tenant_idx", "fund_signals", ["tenant_id"])
    op.create_index(
        "fund_signals_tenant_date_idx", "fund_signals", ["tenant_id", "signal_date"]
    )


def downgrade() -> None:
    """Drop the VC tables in reverse FK order, with their indexes."""
    op.drop_index("fund_signals_tenant_date_idx", "fund_signals")
    op.drop_index("fund_signals_tenant_idx", "fund_signals")
    op.drop_table("fund_signals")

    op.drop_index("deal_opportunities_tenant_activity_idx", "deal_opportunities")
    op.drop_index("deal_opportunities_tenant_idx", "deal_opportunities")
    op.drop_table("deal_opportunities")

    op.drop_index("founders_tenant_contact_idx", "founders")
    op.drop_index("founders_tenant_idx", "founders")
    op.drop_table("founders")
