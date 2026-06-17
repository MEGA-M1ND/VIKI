"""Tests for typed settings."""

from __future__ import annotations

import pytest

from app.core.config import AppEnv, MemoryBackend, Settings


def test_defaults_boot_with_zero_config() -> None:
    settings = Settings()
    assert settings.app_name == "company-brain"
    assert settings.app_env is AppEnv.LOCAL
    assert settings.memory_backend is MemoryBackend.IN_MEMORY
    assert settings.is_production is False


def test_env_prefix_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CB_APP_ENV", "prod")
    monkeypatch.setenv("CB_APP_PORT", "9000")
    settings = Settings()
    assert settings.app_env is AppEnv.PROD
    assert settings.app_port == 9000
    assert settings.is_production is True


def test_default_tenant() -> None:
    assert Settings().default_tenant_id == "default"
