"""Tests for /api/dev/* endpoints.

Covers:
- Gating: endpoints return 404 outside TEST_MODE
- Admin-only access: non-admin users receive 403
- /api/dev/health-dev: public health check
- /api/dev/stats: returns dev configuration and row counts
- /api/dev/reset: clears tables and returns counts
- /api/dev/check-limits: reports over-limit tables
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routers import dev as dev_router

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_headers(test_admin):
    return {"Authorization": f"Bearer dev-token-{test_admin['id']}"}


def _user_headers(test_user):
    return {"Authorization": f"Bearer dev-token-{test_user['id']}"}


class _TestModeOffSettings:
    TEST_MODE = False


# ---------------------------------------------------------------------------
# Gating: dev endpoints are only available in TEST_MODE
# ---------------------------------------------------------------------------


def test_health_dev_available_in_test_mode(client):
    """health-dev returns 200 when TEST_MODE is active."""
    response = client.get("/api/dev/health-dev")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "dev"


def test_health_dev_unavailable_outside_test_mode(clean_database, monkeypatch):
    """health-dev returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db

    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    monkeypatch.setenv("TEST_MODE", "false")
    response = test_client.get("/api/dev/health-dev")
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_stats_unavailable_outside_test_mode(clean_database, test_admin, monkeypatch):
    """stats returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db

    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    monkeypatch.setattr(dev_router, "load_settings_from_env", _TestModeOffSettings)
    response = test_client.get("/api/dev/stats", headers=_admin_headers(test_admin))
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_reset_unavailable_outside_test_mode(clean_database, test_admin, monkeypatch):
    """reset returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db

    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    monkeypatch.setattr(dev_router, "load_settings_from_env", _TestModeOffSettings)
    response = test_client.post("/api/dev/reset", headers=_admin_headers(test_admin))
    app.dependency_overrides.clear()
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin-only access
# ---------------------------------------------------------------------------


def test_stats_requires_admin(client, test_user):
    """stats returns 403 for a non-admin user."""
    response = client.get("/api/dev/stats", headers=_user_headers(test_user))
    assert response.status_code == 403


def test_reset_requires_admin(client, test_user):
    """reset returns 403 for a non-admin user."""
    response = client.post("/api/dev/reset", headers=_user_headers(test_user))
    assert response.status_code == 403


def test_check_limits_requires_admin(client, test_user):
    """check-limits returns 403 for a non-admin user."""
    response = client.get("/api/dev/check-limits", headers=_user_headers(test_user))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /api/dev/stats
# ---------------------------------------------------------------------------


def test_stats_returns_dev_config(client, test_admin):
    """stats returns mode, max_rows_per_table, test_scraper_limit, and tables dict."""
    response = client.get("/api/dev/stats", headers=_admin_headers(test_admin))
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "dev"
    assert "max_rows_per_table" in data
    assert "test_scraper_limit" in data
    assert "tables" in data
    # Should include at least the main tables
    assert "products" in data["tables"]
    assert "users" in data["tables"]


# ---------------------------------------------------------------------------
# /api/dev/reset
# ---------------------------------------------------------------------------


def test_reset_clears_tables(client, test_admin, test_product):
    """reset returns status='reset' with non-zero deleted row counts."""
    response = client.post("/api/dev/reset", headers=_admin_headers(test_admin))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset"
    assert "cleared_tables" in data
    assert "total_rows_deleted" in data
    assert isinstance(data["total_rows_deleted"], int)
    assert data["total_rows_deleted"] > 0
    assert data["cleared_tables"]["products"] >= 1
    assert data["cleared_tables"]["users"] >= 1


# ---------------------------------------------------------------------------
# /api/dev/check-limits
# ---------------------------------------------------------------------------


def test_check_limits_ok_when_within_limit(client, test_admin):
    """check-limits returns 200 when all tables are within the configured limit."""
    response = client.get("/api/dev/check-limits", headers=_admin_headers(test_admin))
    # After a clean seed the tables should be well under the 40-row default.
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_check_limits_returns_400_when_exceeded(client, test_admin, clean_database):
    """check-limits returns 400 with details when any table exceeds the limit."""

    max_rows = clean_database.settings.DEV_MODE_MAX_ROWS_PER_TABLE
    count_resp = clean_database.supabase.table("products").select("id", count="exact").execute()
    current_count = count_resp.count or 0
    to_add = max_rows - current_count + 1

    admin_user = clean_database.table("users").select("id").eq("username", "admin_user").execute()
    admin_id = admin_user.data[0]["id"]

    overflow_rows = [
        {
            "name": f"Overflow Product {i}",
            "description": "Synthetic row for dev limit integration test",
            "source": "github",
            "type": "Software",
            "url": f"https://github.com/test/overflow-{uuid4()}",
            "slug": f"overflow-{uuid4()}",
            "created_by": admin_id,
        }
        for i in range(to_add)
    ]
    clean_database.supabase.table("products").insert(overflow_rows).execute()

    response = client.get("/api/dev/check-limits", headers=_admin_headers(test_admin))
    assert response.status_code == 400
    assert "Dev row limits exceeded" in response.json()["detail"]
    assert "products:" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/dev/test-auth/login
# ---------------------------------------------------------------------------


def test_test_auth_login_resolves_exact_user_identity(client, test_user):
    """test-auth/login returns a UUID dev token bound to the requested user."""
    payload = {"user_id": test_user["id"]}
    response = client.post("/api/dev/test-auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == f"dev-token-{test_user['id']}"
    assert data["token_type"] == "Bearer"
    assert data["created"] is False
    assert data["user"]["id"] == test_user["id"]

    me_resp = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == test_user["id"]


def test_test_auth_login_creates_user_when_requested(client):
    """test-auth/login can create and authenticate a non-seeded test user."""
    payload = {
        "username": f"frontend_test_{uuid4().hex[:8]}",
        "email": f"frontend-test-{uuid4().hex[:8]}@a11yhood.test",
        "create_if_missing": True,
        "role": "user",
    }
    response = client.post("/api/dev/test-auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["created"] is True
    assert data["access_token"].startswith("dev-token-")
    assert data["user"]["username"] == payload["username"]

    me_resp = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == payload["username"]
    assert me_data["email"] == payload["email"]


def test_test_auth_login_requires_identifier(client):
    """test-auth/login requires at least one user identifier."""
    response = client.post("/api/dev/test-auth/login", json={})
    assert response.status_code == 400
    assert "One of user_id, username, or email is required" in response.json()["detail"]
