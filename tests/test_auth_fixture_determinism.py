"""Guards for deterministic auth fixtures used by integration tests."""

import pytest

pytestmark = pytest.mark.integration


def test_auth_client_resolves_seeded_regular_user(auth_client, test_user):
    """auth_client should always authenticate as the seeded regular user."""
    response = auth_client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user["id"]
    assert data["username"] == test_user["username"]
    assert data["role"] == "user"


def test_admin_client_resolves_seeded_admin_user(admin_client, test_admin):
    """admin_client should always authenticate as the seeded admin user."""
    response = admin_client.get("/api/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_admin["id"]
    assert data["username"] == test_admin["username"]
    assert data["role"] == "admin"
