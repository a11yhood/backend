"""
Seed a deterministic test image and attach it to the seeded test product.

Creates one image row and links it to product slug `test-product`.
Designed to be idempotent and safe to re-run.

Run with: uv run python seed_scripts/seed_test_image.py
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

# Fixed ID for deterministic local/dev references.
TEST_IMAGE_ID = "f2b7a5b1-69e8-48ab-a594-14f038bbf3c2"
TEST_IMAGE_KEY = "seed:test-product:image:1"
TEST_IMAGE_URL = "https://example.com/assets/test-product-image.png"
TEST_IMAGE_ALT = "Seeded preview image for Test Product"
ADMIN_USER_ID = "49366adb-2d13-412f-9ae5-4c35dbffab10"
PRODUCT_SLUG = "test-product"

# Canonical seed rows shared with seed_test_users.py and tests/test_data.py
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


def _ensure_seed_users_exist(db) -> None:
    """Ensure deterministic seed users exist for FK-backed seed records."""
    db.table("users").upsert(TEST_USERS, on_conflict="id").execute()
    verify = db.table("users").select("id").eq("id", ADMIN_USER_ID).limit(1).execute()
    if not verify.data:
        raise RuntimeError(
            f"Admin seed user {ADMIN_USER_ID} missing after upsert; cannot satisfy images.created_by FK"
        )


def seed_image() -> None:
    """Upsert a deterministic image and attach it to the seeded test product."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print("Creating test image...\n")

    # Shared test DBs can occasionally miss FK parents after cleanup; recreate deterministically.
    _ensure_seed_users_exist(db)

    image_row = {
        "id": TEST_IMAGE_ID,
        "canonical_key": TEST_IMAGE_KEY,
        "canonical_url": TEST_IMAGE_URL,
        "source_kind": "external",
        "mime_type": "image/png",
        "default_alt": TEST_IMAGE_ALT,
        "created_by": ADMIN_USER_ID,
    }

    try:
        result = db.table("images").upsert(image_row, on_conflict="canonical_key").execute()
        if not result.data:
            lookup = db.table("images").select("id").eq("canonical_key", TEST_IMAGE_KEY).execute()
            if not lookup.data:
                raise RuntimeError("Image upsert completed but no image row was returned or found")
            image_id = lookup.data[0]["id"]
        else:
            image_id = result.data[0]["id"]

        print(f"  ✓ Image seeded (ID: {image_id}, key: {TEST_IMAGE_KEY})")
    except Exception as exc:
        print(f"  ✗ Image seed failed: {exc}")
        raise

    try:
        product_result = db.table("products").select("id,slug").eq("slug", PRODUCT_SLUG).limit(1).execute()
        if not product_result.data:
            print(f"  ! Product '{PRODUCT_SLUG}' not found; image created but not linked")
            return

        product_id = product_result.data[0]["id"]
        db.table("products").update({"image_id": image_id, "image_alt": TEST_IMAGE_ALT}).eq(
            "id", product_id
        ).execute()
        print(f"  ✓ Linked image to product '{PRODUCT_SLUG}' (ID: {product_id})")
    except Exception as exc:
        print(f"  ✗ Failed to link image to product '{PRODUCT_SLUG}': {exc}")
        raise

    print("\n✓ Test image seeding complete!")


if __name__ == "__main__":
    seed_image()
