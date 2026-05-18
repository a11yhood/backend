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

from config import get_settings
from database_adapter import DatabaseAdapter
from services.id_generator import normalize_to_snake_case

env_file = os.getenv("ENV_FILE", ".env.test")
load_dotenv(env_file, override=True)


TEST_USERS = [
    {
        "id": "49366adb-2d13-412f-9ae5-4c35dbffab10",
        "github_id": "admin-test-001",
        "username": "admin_user",
        "display_name": "Admin User",
        "email": "admin@example.com",
        "role": "admin",
    },
    {
        "id": "94e116f7-885d-4d32-87ae-697c5dc09b9e",
        "github_id": "mod-test-002",
        "username": "moderator_user",
        "display_name": "Moderator User",
        "email": "moderator@example.com",
        "role": "moderator",
    },
    {
        "id": "2a3b7c3e-971b-4b42-9c8c-0f1843486c50",
        "github_id": "user-test-003",
        "username": "regular_user",
        "display_name": "Regular User",
        "email": "user@example.com",
        "role": "user",
    },
]


def _ensure_seed_users(db) -> None:
    """Ensure canonical test users exist before creating products/tags."""
    db.table("users").upsert(TEST_USERS, on_conflict="id").execute()


def seed_product():
    """Upsert a test product (and its tags) into the database."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    _ensure_seed_users(db)

    print("Creating test product...\n")

    product_name = "Test Product"
    product_url = "https://github.com/test/product"
    product_slug = normalize_to_snake_case(product_name)
    tag_names = ["accessibility", "testing"]

    # Upsert product (conflict on slug for deterministic test identity)
    product_data = {
        "name": product_name,
        "source_url": product_url,
        "slug": product_slug,
        "type": "Software",
        "source": "github",
        "description": "A test product for accessibility",
    }
    try:
        db.table("products").upsert(product_data, on_conflict="slug").execute()
        product_result = db.table("products").select("id,slug").eq("slug", product_slug).limit(1).execute()
        if not product_result.data:
            print("  ? Product upsert completed but product not found by slug")
            return
        product = product_result.data[0]
        print(f"  ✓ Product: {product_name} (ID: {product['id']}, Slug: {product['slug']})")
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
