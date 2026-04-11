"""
Seed OAuth configs for scraper platforms.

Populates the oauth_configs table with placeholder platform configurations.
In production, OAuth configs should be managed via the admin UI or environment variables.

Run with: uv run python seed_scripts/seed_oauth_configs.py
"""

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv

env_file = os.getenv("ENV_FILE", ".env.test")
load_dotenv(env_file, override=True)

from config import get_settings
from database_adapter import DatabaseAdapter


def _env(name: str, default: str | None = None) -> str | None:
    """Read env var and strip leading/trailing whitespace."""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _first_env(names: list[str], default: str | None = None) -> str | None:
    """Return the first non-empty value among a list of env var names."""
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    return default

OAUTH_CONFIGS = [
    {
        "platform": "ravelry",
        "client_id": _env("RAVELRY_APP_KEY", "PLACEHOLDER_CLIENT_ID"),
        "client_secret": _env("RAVELRY_APP_SECRET", "PLACEHOLDER_CLIENT_SECRET"),
        "redirect_uri": _env(
            "RAVELRY_REDIRECT_URI",
            "http://localhost:8000/api/scrapers/oauth/ravelry/callback",
        ),
        "access_token": _first_env([
            "RAVELRY_ACCESS_TOKEN",
            "RAVELRY_OAUTH_ACCESS_TOKEN",
            "RAVELRY_OAUTH_TOKEN",
            "RAVELRY_TOKEN",
            "RAVELRY_ACCESS",
            "ACCESS_TOKEN_RAVELRY",
            "RAVELRY_TOKEN_VALUE",
            "RAVELRY_AUTH_TOKEN",
            "ACCESS_TOKEN",
        ]),
        "refresh_token": _first_env([
            "RAVELRY_REFRESH_TOKEN",
            "RAVELRY_OAUTH_REFRESH_TOKEN",
            "RAVELRY_TOKEN_REFRESH",
            "RAVELRY_REFRESH",
            "REFRESH_TOKEN_RAVELRY",
            "RAVELRY_TOKEN_REFRESH_VALUE",
            "RAVELRY_AUTH_REFRESH_TOKEN",
            "REFRESH_TOKEN",
        ]),
    },
    {
        "platform": "thingiverse",
        "client_id": _env("THINGIVERSE_CLIENT_ID", "PLACEHOLDER_CLIENT_ID"),
        "client_secret": _env("THINGIVERSE_CLIENT_SECRET", "PLACEHOLDER_CLIENT_SECRET"),
        "redirect_uri": _env(
            "THINGIVERSE_REDIRECT_URI",
            "http://localhost:8000/api/scrapers/oauth/thingiverse/callback",
        ),
        "access_token": _env("THINGIVERSE_ACCESS_TOKEN"),
        "refresh_token": _env("THINGIVERSE_REFRESH_TOKEN"),
    },
    {
        "platform": "github",
        "client_id": _env("GITHUB_CLIENT_ID", "PLACEHOLDER_CLIENT_ID"),
        "client_secret": _env("GITHUB_CLIENT_SECRET", "PLACEHOLDER_CLIENT_SECRET"),
        "redirect_uri": _env(
            "GITHUB_REDIRECT_URI",
            "http://localhost:8000/api/auth/callback",
        ),
        "access_token": _env("GITHUB_ACCESS_TOKEN"),
        "refresh_token": _env("GITHUB_REFRESH_TOKEN"),
    },
]


def seed_oauth_configs():
    """Upsert OAuth configs into the database."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print("Seeding oauth_configs table...")

    upserted = 0
    for config in OAUTH_CONFIGS:
        try:
            result = db.table("oauth_configs").upsert(
                config, on_conflict="platform"
            ).execute()
            if result.data:
                upserted += 1
                print(f"  ✓ {config['platform']}")
        except Exception as e:
            print(f"  ✗ {config['platform']}: {e}")

    print(f"✓ OAuth configs seeded: {upserted} upserted")


if __name__ == "__main__":
    seed_oauth_configs()
