"""
Seed initial scraper search terms into Supabase.

Populates scraper_search_terms with one row per platform storing a search_terms array.

Run with: uv run python seed_scripts/seed_scraper_search_terms.py
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

SEEDS = [
    {
        "platform": "github",
        "search_terms": [
            "assistive technology",
            "screen reader",
            "eye tracking",
            "speech recognition",
            "switch access",
            "alternative input",
            "text-to-speech",
            "voice control",
            "accessibility aid",
            "mobility aid software",
        ],
    },
    {
        "platform": "thingiverse",
        "search_terms": [
            "accessibility",
            "assistive+device",
            "arthritis+grip",
            "adaptive+tool",
            "mobility+aid",
            "tremor+stabilizer",
            "adaptive+utensil",
        ],
    },
    {
        "platform": "ravelry_pa_categories",
        "search_terms": [
            "medical-device-access",
            "medical-device-accessory",
            "mobility-aid-accessory",
            "other-accessibility",
            "adaptive",
            "therapy-aid",
        ],
    },
]


def main():
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print("Seeding scraper_search_terms table...")

    # Insert individual terms (normalized format after 20251228 migration)
    # The table now has one row per search_term, not an array
    count = 0
    for seed in SEEDS:
        platform = seed["platform"]
        for term in seed["search_terms"]:
            try:
                result = (
                    db.table("scraper_search_terms")
                    .upsert(
                        {"platform": platform, "search_term": term},
                        on_conflict="platform,search_term",
                    )
                    .execute()
                )
                if result.data:
                    count += 1
            except Exception as e:
                print(f"  ✗ {platform}/{term}: {e}")

    print(f"✓ Scraper search terms seeded. ({count} terms)")


if __name__ == "__main__":
    main()
