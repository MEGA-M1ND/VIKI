from typing import TypedDict, Literal

from src.connectors.base import RawDocument


class ExtractionState(TypedDict):
    # Input
    document: RawDocument

    # Classification stage
    is_worth_remembering: bool | None
    classifier_reasoning: str | None
    confidence: float | None

    # Extraction stage
    extracted_facts: list[dict] | None
    entities: list[dict] | None
    summary: str | None

    # Deduplication stage
    existing_similar_pages: list[dict] | None
    is_duplicate: bool | None

    # Write stage
    gbrain_page_slug: str | None
    write_status: Literal["success", "skipped", "failed"] | None
    error: str | None
