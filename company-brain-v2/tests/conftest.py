"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Settings with deterministic local defaults for tests."""
    return Settings(app_env="local", memory_backend="in_memory", log_json=False)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient that runs the app lifespan (wires the container)."""
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
