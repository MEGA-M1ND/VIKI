"""VC fund intelligence domain models (Phase 2).

These models represent the durable entities of the VC Intelligence Layer:
founders, deal opportunities, and fund signals. They inherit from
:class:`~app.models.common.DomainModel` (extra="forbid", validate_assignment)
but additionally enable ``from_attributes=True`` so they can be constructed
directly from SQLAlchemy ORM rows (``Model.model_validate(row)``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field

from app.models.common import DomainModel
from app.utils.ids import utcnow


class FounderProfile(DomainModel):
    """A founder tracked by the fund, with a computed engagement signal score.

    Attributes:
        id: Internal unique id.
        tenant_id: Owning tenant — the partition key for all retrieval.
        full_name: Founder's full name.
        company_name: Name of the founder's company.
        stage: Fundraising stage.
        domain: Sector/domain such as "fintech", "deeptech", "saas".
        location: Free-form location string.
        last_contact_date: Most recent contact timestamp.
        signal_score: Computed engagement score in [0, 1].
        raw_signals: Free-form signal descriptions kept for traceability.
        source_doc_ids: Source documents this profile was derived from.
        created_at: First persisted.
        updated_at: Last mutated.
    """

    model_config = ConfigDict(**DomainModel.model_config, from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    full_name: str
    company_name: str
    stage: Literal["idea", "pre-seed", "seed", "series-a", "series-b+"]
    domain: str
    location: str
    last_contact_date: datetime
    signal_score: float = 0.0
    raw_signals: list[str] = Field(default_factory=list)
    source_doc_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DealOpportunity(DomainModel):
    """A potential or active deal tied to a founder.

    Attributes:
        id: Internal unique id.
        tenant_id: Owning tenant.
        founder_id: The :class:`FounderProfile` this deal belongs to.
        company_name: Name of the company being evaluated.
        deal_stage: Pipeline stage.
        raise_amount_usd: Round size in USD, if known.
        last_activity_date: Most recent activity timestamp.
        next_action: Free-form next step, if any.
        source_doc_ids: Source documents this deal was derived from.
    """

    model_config = ConfigDict(**DomainModel.model_config, from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    founder_id: UUID
    company_name: str
    deal_stage: Literal["cold", "warm", "active", "passed", "portfolio"]
    raise_amount_usd: float | None = None
    last_activity_date: datetime
    next_action: str | None = None
    source_doc_ids: list[str] = Field(default_factory=list)


class FundSignal(DomainModel):
    """A single dated interaction signal feeding the founder signal score.

    Attributes:
        id: Internal unique id.
        tenant_id: Owning tenant.
        signal_type: Kind of interaction.
        founder_id: The associated founder, if known.
        company_name: Company referenced by the signal.
        signal_date: When the signal occurred.
        raw_text: Original text the signal was extracted from.
        confidence: Extractor confidence in [0, 1].
    """

    model_config = ConfigDict(**DomainModel.model_config, from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    signal_type: Literal[
        "outreach",
        "follow_up",
        "deck_shared",
        "meeting_requested",
        "term_sheet",
        "pass",
    ]
    founder_id: UUID | None = None
    company_name: str
    signal_date: datetime
    raw_text: str
    confidence: float
