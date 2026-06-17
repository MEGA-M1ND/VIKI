"""Ingestion stage: extracting and persisting durable facts."""

from app.ingestion.base import BaseExtractor
from app.ingestion.orchestrator import IngestionOrchestrator, IngestionStats

__all__ = ["BaseExtractor", "IngestionOrchestrator", "IngestionStats"]
