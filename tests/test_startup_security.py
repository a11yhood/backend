"""Test startup security validation.

Ensures that TEST_MODE and default SECRET_KEY are rejected in production-like environments.
"""

import pytest


def _set_env(monkeypatch, values: dict[str, str]) -> None:
    """Set env vars for one test case."""
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_test_mode_rejected_in_production_with_supabase(monkeypatch):
    """TEST_MODE should be rejected when Supabase config is explicitly marked production."""
    _set_env(
        monkeypatch,
        {
            "TEST_MODE": "true",
            "SUPABASE_URL": "https://myproject.supabase.co",
            "SUPABASE_KEY": "real-key",
            "ENVIRONMENT": "production",
        },
    )
    # Reload config to pick up env changes
    from importlib import reload

    import config

    reload(config)

    # Try to start app
    with pytest.raises(RuntimeError, match="TEST_MODE=true in production"):
        # Trigger startup event
        import asyncio

        from main import validate_security_configuration

        asyncio.run(validate_security_configuration())


def test_test_mode_rejected_in_production_with_production_url(monkeypatch):
    """TEST_MODE should be rejected when PRODUCTION_URL is set"""
    _set_env(
        monkeypatch,
        {
            "TEST_MODE": "true",
            "PRODUCTION_URL": "https://a11yhood.com",
        },
    )
    from importlib import reload

    import config

    reload(config)

    with pytest.raises(RuntimeError, match="TEST_MODE=true in production"):
        import asyncio

        from main import validate_security_configuration

        asyncio.run(validate_security_configuration())


def test_test_mode_rejected_with_environment_variable(monkeypatch):
    """TEST_MODE should be rejected when ENVIRONMENT=production"""
    _set_env(
        monkeypatch,
        {
            "TEST_MODE": "true",
            "ENVIRONMENT": "production",
        },
    )
    from importlib import reload

    import config

    reload(config)

    with pytest.raises(RuntimeError, match="TEST_MODE=true in production"):
        import asyncio

        from main import validate_security_configuration

        asyncio.run(validate_security_configuration())


def test_default_secret_key_rejected_in_production(monkeypatch):
    """Default SECRET_KEY should be rejected in production"""
    _set_env(
        monkeypatch,
        {
            "SECRET_KEY": "dev-secret-key-change-in-production",
            "SUPABASE_URL": "https://myproject.supabase.co",
            "TEST_MODE": "false",
            "ENVIRONMENT": "production",
        },
    )
    from importlib import reload

    import config

    reload(config)

    with pytest.raises(RuntimeError, match="Default SECRET_KEY in production"):
        import asyncio

        from main import validate_security_configuration

        asyncio.run(validate_security_configuration())


def test_short_secret_key_rejected_in_production(monkeypatch):
    """Short SECRET_KEY should be rejected in production"""
    _set_env(
        monkeypatch,
        {
            "SECRET_KEY": "short",
            "SUPABASE_URL": "https://myproject.supabase.co",
            "TEST_MODE": "false",
            "ENVIRONMENT": "production",
        },
    )
    from importlib import reload

    import config

    reload(config)

    with pytest.raises(RuntimeError, match="SECRET_KEY too short"):
        import asyncio

        from main import validate_security_configuration

        asyncio.run(validate_security_configuration())


def test_test_mode_allowed_in_development(monkeypatch):
    """TEST_MODE should be allowed when no production indicators present"""
    _set_env(
        monkeypatch,
        {
            "TEST_MODE": "true",
            "SUPABASE_URL": "https://dummy.supabase.co",
            "PRODUCTION_URL": "",
            "ENVIRONMENT": "development",
        },
    )
    from importlib import reload

    import config

    reload(config)

    # Should not raise
    import asyncio

    from main import validate_security_configuration

    asyncio.run(validate_security_configuration())


def test_production_with_valid_config_succeeds(monkeypatch):
    """Production with proper SECRET_KEY should work"""
    _set_env(
        monkeypatch,
        {
            "TEST_MODE": "false",
            "SECRET_KEY": "a" * 64,  # Long secure key
            "SUPABASE_URL": "https://myproject.supabase.co",
            "ENVIRONMENT": "production",
        },
    )
    from importlib import reload

    import config

    reload(config)

    # Should not raise
    import asyncio

    from main import validate_security_configuration

    asyncio.run(validate_security_configuration())
