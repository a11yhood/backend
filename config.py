"""Configuration management for a11yhood backend.

Loads settings from .env file with Pydantic validation.
Always uses Supabase - point .env at the production project, .env.test at the test project.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Validates and provides defaults for all configuration values.
    SUPABASE_URL/KEY are required; point them at the appropriate Supabase project.
    """

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    # Supabase (required for both production and test environments)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # service_role key for backend
    SUPABASE_ANON_KEY: str = ""  # anon/public key
    SUPABASE_POSTGREST_TIMEOUT: int = 180

    # CORS - strict allowlist for security
    # Dev: Uses Vite proxy (https://localhost:5173 -> http://localhost:8000)
    # Prod: Set to actual frontend domain (e.g., https://a11yhood.com)
    FRONTEND_URL: str = "https://localhost:4173"
    PRODUCTION_URL: str = ""
    CORS_EXTRA_ORIGINS: str = ""  # Comma-separated additional origins
    ALLOWED_HOSTS: str = ""  # Comma-separated host allowlist for TrustedHostMiddleware

    # Environment mode (development, staging, production)
    ENVIRONMENT: str | None = None  # 'production', 'staging', 'development'

    # Test mode settings
    TEST_MODE: bool = False
    TEST_SCRAPER_LIMIT: int = 5

    # Dev mode features
    DEV_MODE_MAX_ROWS_PER_TABLE: int = 40  # Max rows per table in dev mode
    DEV_TEST_AUTH_SECRET: str | None = None  # Optional shared secret for /api/dev/test-auth/login

    # GitHub API token for higher rate limits (optional)
    GITHUB_TOKEN: str | None = None

    # Secret key for JWT
    SECRET_KEY: str = "dev-secret-key-change-in-production"

    # OAuth (optional)
    THINGIVERSE_APP_ID: str | None = None
    RAVELRY_APP_KEY: str | None = None
    RAVELRY_APP_SECRET: str | None = None
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None

    def model_post_init(self, ctx):
        # Only derive TEST_MODE from ENVIRONMENT when it was not explicitly set
        if "TEST_MODE" not in self.model_fields_set:
            self.TEST_MODE = self.ENVIRONMENT == "development"


@lru_cache
def get_settings(env_file: str = ".env") -> Settings:
    """Get cached settings instance.

    Uses LRU cache to avoid re-parsing .env on every import.
    Allows env_file override for testing with isolated configurations.
    """
    return Settings(_env_file=env_file)


def load_settings_from_env() -> Settings:
    """Load a fresh settings instance reflecting current environment variables.

    Bypasses the cached settings so tests that patch os.environ see updated values.
    """
    return Settings(_env_file=os.getenv("ENV_FILE", ".env"))


# Default settings instance (respects ENV_FILE when set)
settings = get_settings(os.getenv("ENV_FILE", ".env"))
