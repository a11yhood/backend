"""
Seed test users into Supabase.

Creates three test users with fixed IDs that match DEV_USER_IDS in services/auth.py:
  1. Admin user
  2. Moderator user
  3. Regular user

Run with: uv run python seed_scripts/seed_test_users.py
"""

import os
import sys

# Ensure the project root is on sys.path when run directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv

env_file = os.getenv("ENV_FILE", ".env.test")
load_dotenv(env_file, override=True)

from config import get_settings
from database_adapter import DatabaseAdapter

# Fixed IDs that match DEV_USER_IDS in services/auth.py and TEST_USERS in tests/test_data.py
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


def seed_users():
    """Upsert test users into the database."""
    settings = get_settings(env_file)
    db = DatabaseAdapter(settings)

    print(f"Using Supabase: {settings.SUPABASE_URL}")

    print("Upserting test users...\n")

    for user in TEST_USERS:
        try:
            result = db.table("users").upsert(user).execute()
            if result.data:
                print(f"  ✓ {user['role']}: {user['username']} (ID: {user['id']})")
            else:
                print(f"  ? {user['username']}: no data returned")
        except Exception as e:
            print(f"  ✗ {user['username']}: {e}")

    print("\n✓ Test users seeding complete!")
    print("\nTest Accounts:")
    print("-" * 70)
    print(f"{'Role':<12} | {'Username':<18} | {'Email':<25} | {'GitHub ID'}")
    print("-" * 70)
    for user in TEST_USERS:
        print(
            f"{user['role']:<12} | {user['username']:<18} | {user['email']:<25} | {user['github_id']}"
        )
    print("-" * 70)


if __name__ == "__main__":
    seed_users()
