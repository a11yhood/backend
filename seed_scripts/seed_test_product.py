"""
Seed a test product into Supabase.

Creates one test product with tags for testing.

Run with: uv run python seed_scripts/seed_test_product.py
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
from services.id_generator import normalize_to_snake_case


def seed_product():
    """Upsert a test product (and its tags) into the database."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print("Creating test product...\n")

    product_name = "Test Product"
    product_url = "https://github.com/test/product"
    product_slug = normalize_to_snake_case(product_name)
    tag_names = ["accessibility", "testing"]

    # Upsert product (conflict on source_url)
    product_data = {
        "name": product_name,
        "source_url": product_url,
        "slug": product_slug,
        "type": "Software",
        "source": "github",
        "description": "A test product for accessibility",
    }
    try:
        result = db.table("products").upsert(product_data, on_conflict="source_url").execute()
        if result.data:
            product = result.data[0]
            print(f"  ✓ Product: {product_name} (ID: {product['id']}, Slug: {product['slug']})")
        else:
            print("  ? Product upsert returned no data")
            return
    except Exception as e:
        print(f"  ✗ Product: {e}")
        sys.exit(1)

    product_id = product["id"]

    # Ensure tags exist and are linked
    for tag_name in tag_names:
        try:
            tag_result = db.table("tags").upsert({"name": tag_name}, on_conflict="name").execute()
            if not tag_result.data:
                tag_result = db.table("tags").select("*").eq("name", tag_name).execute()
            tag = tag_result.data[0]

            db.table("product_tags").upsert(
                {"product_id": product_id, "tag_id": tag["id"]},
                on_conflict="product_id,tag_id",
            ).execute()
            print(f"  ✓ Tag: {tag_name}")
        except Exception as e:
            print(f"  ✗ Tag '{tag_name}': {e}")

    print("\n✓ Test product seeding complete!")


if __name__ == "__main__":
    seed_product()
