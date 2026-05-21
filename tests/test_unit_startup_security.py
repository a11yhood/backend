"""Unit tests for startup security predicates/validation."""

import asyncio

import pytest

import main

pytestmark = pytest.mark.unit


class _Settings:
    def __init__(
        self,
        *,
        environment="development",
        production_url="",
        supabase_url="https://dummy.supabase.co",
        test_mode=False,
        secret_key="x" * 64,
    ):
        self.ENVIRONMENT = environment
        self.PRODUCTION_URL = production_url
        self.SUPABASE_URL = supabase_url
        self.TEST_MODE = test_mode
        self.SECRET_KEY = secret_key
        self.TEST_SCRAPER_LIMIT = 20
        self.DEV_MODE_MAX_ROWS_PER_TABLE = 40


class _NoopScheduler:
    def initialize(self, _db):
        return None

    def start(self):
        return None


def test_has_production_indicators_true_when_environment_is_production(monkeypatch):
    settings = _Settings(
        environment="development",
        production_url="",
        supabase_url="https://myproject.supabase.co",
        test_mode=False,
        secret_key="dev-secret-key-change-in-production",
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(main, "load_settings_from_env", lambda: settings)
    monkeypatch.setattr(main, "get_cors_origins", lambda: ["http://localhost:5173"])
    monkeypatch.setattr(main, "get_scheduled_scraper_service", _NoopScheduler)
    monkeypatch.setattr(main, "get_db", object)

    with pytest.raises(RuntimeError, match="Default SECRET_KEY in production"):
        asyncio.run(main.validate_security_configuration())


def test_has_production_indicators_true_when_env_var_is_production(monkeypatch):
    settings = _Settings(
        environment="development",
        production_url="https://a11yhood.org",
        supabase_url="https://myproject.supabase.co",
        test_mode=False,
        secret_key="dev-secret-key-change-in-production",
    )
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(main, "load_settings_from_env", lambda: settings)
    monkeypatch.setattr(main, "get_cors_origins", lambda: ["http://localhost:5173"])
    monkeypatch.setattr(main, "get_scheduled_scraper_service", _NoopScheduler)
    monkeypatch.setattr(main, "get_db", object)

    with pytest.raises(RuntimeError, match="Default SECRET_KEY in production"):
        asyncio.run(main.validate_security_configuration())


def test_has_production_indicators_false_with_local_production_url(monkeypatch):
    settings = _Settings(
        environment="development",
        production_url="http://localhost:8000",
        supabase_url="https://dummy.supabase.co",
        test_mode=False,
        secret_key="dev-secret-key-change-in-production",
    )
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(main, "load_settings_from_env", lambda: settings)
    monkeypatch.setattr(main, "get_cors_origins", lambda: ["http://localhost:5173"])
    monkeypatch.setattr(main, "get_scheduled_scraper_service", _NoopScheduler)
    monkeypatch.setattr(main, "get_db", object)

    # Should not raise: localhost production URL is treated as development-like.
    asyncio.run(main.validate_security_configuration())


def test_validate_security_configuration_rejects_default_secret_in_production(monkeypatch):
    settings = _Settings(
        environment="production",
        supabase_url="https://myproject.supabase.co",
        test_mode=False,
        secret_key="dev-secret-key-change-in-production",
    )
    monkeypatch.setattr(main, "load_settings_from_env", lambda: settings)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(main, "get_cors_origins", lambda: ["http://localhost:5173"])
    monkeypatch.setattr(main, "get_scheduled_scraper_service", _NoopScheduler)
    monkeypatch.setattr(main, "get_db", object)

    with pytest.raises(RuntimeError, match="Default SECRET_KEY in production"):
        asyncio.run(main.validate_security_configuration())


def test_validate_security_configuration_allows_test_mode_in_dev(monkeypatch):
    settings = _Settings(
        environment="development",
        production_url="",
        supabase_url="https://dummy.supabase.co",
        test_mode=True,
        secret_key="dev-secret-key-change-in-production",
    )
    monkeypatch.setattr(main, "load_settings_from_env", lambda: settings)
    monkeypatch.setattr(main, "get_cors_origins", lambda: ["http://localhost:5173"])

    # Should not raise
    asyncio.run(main.validate_security_configuration())
