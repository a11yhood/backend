"""Test user account endpoints"""

import pytest
import uuid
from datetime import datetime

pytestmark = pytest.mark.integration


def test_get_user_account_with_joined_and_last_active(client, clean_database, test_user):
    """Test that user account endpoint returns joined_at and last_active timestamps"""
    response = client.get(f"/api/users/{test_user['id']}")

    assert response.status_code == 200
    data = response.json()

    # Check all expected fields are present
    assert data["id"] == test_user["id"]
    assert "username" in data
    assert data["role"] == "user"

    # Check timestamp fields (backend uses snake_case)
    assert "created_at" in data
    assert "joined_at" in data
    assert "last_active" in data

    # Timestamps should be ISO format strings
    if data.get("joined_at"):
        # Should be parseable as datetime
        datetime.fromisoformat(data["joined_at"].replace("Z", "+00:00"))

    if data.get("last_active"):
        # Should be parseable as datetime
        datetime.fromisoformat(data["last_active"].replace("Z", "+00:00"))


def test_create_user_account_with_timestamps(client, clean_database):
    """Test that creating a user account returns joined_at and last_active"""
    user_id = str(uuid.uuid4())

    response = client.put(
        f"/api/users/{user_id}",
        json={
            "username": "newuser",
            "avatar_url": "https://example.com/avatar.jpg",
            "email": "new@example.com",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Check fields
    assert data["id"] == user_id
    assert data["username"] == "newuser"
    assert data["email"] == "new@example.com"

    # Check timestamp fields exist (backend uses snake_case)
    assert "created_at" in data
    assert "joined_at" in data
    assert "last_active" in data


def test_update_user_profile_preserves_timestamps(auth_client, clean_database, test_user):
    """Test that updating user profile preserves original joined_at and updates last_active"""
    # Get initial user data
    response1 = auth_client.get(f"/api/users/{test_user['id']}")
    initial_data = response1.json()
    initial_joined_at = initial_data.get("joined_at")

    # Update profile (using auth_client which has test_user auth)
    response2 = auth_client.patch(
        f"/api/users/{test_user['id']}/profile", json={"display_name": "Updated Name"}
    )

    assert response2.status_code == 200
    updated_data = response2.json()

    # joined_at should not change (backend uses snake_case)
    assert updated_data.get("joined_at") == initial_joined_at

    # last_active should exist (may have updated)
    assert "last_active" in updated_data


def test_user_account_response_includes_all_fields(client, clean_database, test_user):
    """Test that UserAccountResponse includes all expected fields"""
    response = client.get(f"/api/users/{test_user['id']}")

    assert response.status_code == 200
    data = response.json()

    # All expected fields should be present (backend uses snake_case)
    expected_fields = [
        "id",
        "username",
        "role",
        "email",
        "avatar_url",
        "display_name",
        "created_at",
        "joined_at",
        "last_active",
    ]

    for field in expected_fields:
        assert field in data, f"Missing field: {field}"


def test_get_nonexistent_user_returns_404(client):
    """Test that getting a nonexistent user returns 404"""
    response = client.get("/api/users/nonexistent_user_id")
    assert response.status_code == 404


def test_get_current_user_me_endpoint(auth_client, test_user):
    """Test that /api/users/me returns authenticated user's full profile"""
    response = auth_client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()

    # Should return full authenticated user data
    assert data["id"] == test_user["id"]
    assert data["username"] == test_user["username"]
    assert data["role"] == test_user.get("role", "user")
    assert "email" in data  # Full profile includes email
    assert "preferences" in data  # Full profile includes preferences


def test_me_endpoint_requires_auth(client):
    """Test that /api/users/me requires authentication"""
    response = client.get("/api/users/me")
    assert response.status_code == 401


def test_me_endpoint_returns_full_profile_with_email(auth_client, test_user):
    """Test that /api/users/me includes email (unlike public endpoint)"""
    # /api/users/me returns full profile with email
    response = auth_client.get("/api/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.get("email")

    # Public endpoint /api/users/by-username/{username} hides email
    response = auth_client.get(f"/api/users/by-username/{test_user['username']}")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] is None  # Public profile excludes email
