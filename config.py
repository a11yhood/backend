"""Configuration management for a11yhood backend.

Loads settings from .env file with Pydantic validation.
Always uses Supabase - point .env at the production project, .env.test at the test project.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


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
    
    # CORS - strict allowlist for security
    # Dev: Uses Vite proxy (https://localhost:5173 -> http://localhost:8000)
    # Prod: Set to actual frontend domain (e.g., https://a11yhood.com)
    FRONTEND_URL: str = "https://localhost:4173"
    PRODUCTION_URL: str = ""
    CORS_EXTRA_ORIGINS: str = ""  # Comma-separated additional origins
    
    # Environment mode (development, staging, production)
    ENVIRONMENT: Optional[str] = None  # 'production', 'staging', 'development'
    
    # Test mode settings
    TEST_MODE: bool = False
    TEST_SCRAPER_LIMIT: int = 5
    
    # GitHub API token for higher rate limits (optional)
    GITHUB_TOKEN: Optional[str] = None
    
    # Secret key for JWT
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    
    # OAuth (optional)
    THINGIVERSE_APP_ID: Optional[str] = None
    RAVELRY_APP_KEY: Optional[str] = None
    RAVELRY_APP_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    


@lru_cache()
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
