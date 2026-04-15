"""
Seed the supported_sources table with initial data.

Run with: uv run python seed_scripts/seed_supported_sources.py
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

SUPPORTED_SOURCES = [
    {"domain": "ravelry.com", "name": "Ravelry"},
    {"domain": "github.com", "name": "Github"},
    {"domain": "thingiverse.com", "name": "Thingiverse"},
    {"domain": "example.com", "name": "Example"},
]


def seed_supported_sources():
    """Upsert supported sources into the database."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print("Seeding supported_sources table...")

    added = 0
    for source in SUPPORTED_SOURCES:
        try:
            result = db.table("supported_sources").upsert(source, on_conflict="domain").execute()
            if result.data:
                added += 1
                print(f"  ✓ {source['domain']} ({source['name']})")
        except Exception as e:
            print(f"  ✗ {source['domain']}: {e}")

    print(f"✓ Supported sources seeded: {added} upserted")


if __name__ == "__main__":
    seed_supported_sources()
