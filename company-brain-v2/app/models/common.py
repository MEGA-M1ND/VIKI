"""Shared enums and the base model configuration for domain objects."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base class for all domain models.

    Centralizes Pydantic configuration so every model behaves consistently:
    immutable-by-default is *not* enforced (records are updated in place during
    the pipeline), but unknown fields are rejected to catch mapping bugs early.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SourceType(StrEnum):
    """Origin system for an ingested document."""

    GMAIL = "gmail"
    NOTION = "notion"
    SLACK = "slack"


class FactType(StrEnum):
    """Category of a durable extracted fact.

    Kept deliberately small for the MVP; extend as extraction matures.
    """

    FACT = "fact"
    PREFERENCE = "preference"
    ENTITY = "entity"
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    RELATIONSHIP = "relationship"


class EntityType(StrEnum):
    """Type of a named entity referenced by a fact."""

    PERSON = "person"
    COMPANY = "company"
    PROJECT = "project"
    CONCEPT = "concept"
    OTHER = "other"
