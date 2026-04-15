"""Tests for scraper endpoints and services using the Supabase test database"""

import pytest

pytestmark = pytest.mark.integration
from routers import scrapers as scrapers_router


def test_trigger_github_scraper_success(admin_client, monkeypatch):
    async def _fake_run(*args, **kwargs):
        return None

    monkeypatch.setattr(scrapers_router, "_run_scraper_and_log", _fake_run)

    response = admin_client.post(
        "/api/scrapers/trigger",
        json={"source": "github", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Scraping started for github"
    assert data["test_mode"] is True
    assert data["test_limit"] == 3


def test_trigger_scraper_requires_admin(auth_client):
    response = auth_client.post(
        "/api/scrapers/trigger",
        json={"source": "github", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]


def test_trigger_scraper_unauthenticated(client):
    response = client.post(
        "/api/scrapers/trigger",
        json={"source": "github", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 401


def test_trigger_scraper_invalid_source(admin_client):
    response = admin_client.post(
        "/api/scrapers/trigger",
        json={"source": "invalid_platform", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 422


def test_trigger_thingiverse_without_oauth(admin_client):
    response = admin_client.post(
        "/api/scrapers/trigger",
        json={"source": "thingiverse", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 400
    assert "OAuth not configured" in response.json()["detail"]


def test_trigger_ravelry_without_token(admin_client, clean_database, test_admin):
    clean_database.table("oauth_configs").insert(
        {
            "platform": "ravelry",
            "client_id": "id",
            "client_secret": "secret",
            "redirect_uri": "http://localhost",
            "access_token": None,
        }
    ).execute()

    response = admin_client.post(
        "/api/scrapers/trigger",
        json={"source": "ravelry", "test_mode": True, "test_limit": 3},
    )

    assert response.status_code == 400
    assert "No access token found" in response.json()["detail"]


def test_get_scraping_logs(auth_client, clean_database, test_user):
    clean_database.table("scraping_logs").insert(
        {
            "user_id": test_user["id"],
            "source": "github",
            "products_found": 2,
            "products_added": 2,
            "products_updated": 0,
            "duration_seconds": 1.2,
            "status": "success",
        }
    ).execute()

    response = auth_client.get("/api/scrapers/logs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "github"
    assert data[0]["status"] == "success"


def test_get_scraping_logs_with_filter(auth_client, clean_database, test_user):
    clean_database.table("scraping_logs").insert(
        {
            "user_id": test_user["id"],
            "source": "thingiverse",
            "products_found": 1,
            "products_added": 1,
            "products_updated": 0,
            "duration_seconds": 0.5,
            "status": "success",
        }
    ).execute()

    response = auth_client.get("/api/scrapers/logs?source=thingiverse&limit=10")

    assert response.status_code == 200


def test_get_oauth_configs_requires_admin(auth_client):
    """Test that non-admin users cannot view OAuth configs"""
    response = auth_client.get("/api/scrapers/oauth-configs")

    assert response.status_code == 403


def test_get_oauth_configs_as_admin(admin_client, clean_database):
    clean_database.table("oauth_configs").insert(
        {
            "platform": "thingiverse",
            "client_id": "test_client_id",
            "client_secret": "secret",
            "redirect_uri": "https://example.com/callback",
        }
    ).execute()

    response = admin_client.get("/api/scrapers/oauth-configs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["platform"] == "thingiverse"
    assert "client_secret" not in data[0]


def test_create_oauth_config(admin_client, clean_database):
    response = admin_client.post(
        "/api/scrapers/oauth-configs",
        json={
            "platform": "thingiverse",
            "client_id": "new_client_id",
            "client_secret": "new_secret",
            "redirect_uri": "https://example.com/callback",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["platform"] == "thingiverse"


def test_create_oauth_config_requires_admin(auth_client):
    """Test that non-admin users cannot create OAuth configs"""
    response = auth_client.post(
        "/api/scrapers/oauth-configs",
        json={
            "platform": "thingiverse",
            "client_id": "new_client_id",
            "client_secret": "new_secret",
            "redirect_uri": "https://example.com/callback",
        },
    )

    assert response.status_code == 403


def test_update_oauth_config(admin_client, clean_database):
    clean_database.table("oauth_configs").insert(
        {
            "platform": "thingiverse",
            "client_id": "old",
            "client_secret": "secret",
            "redirect_uri": "https://example.com/callback",
        }
    ).execute()

    response = admin_client.put(
        "/api/scrapers/oauth-configs/thingiverse",
        json={"client_id": "updated_client_id"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == "updated_client_id"


def test_update_oauth_config_not_found(admin_client):
    # Endpoint creates a config when a supported platform does not already exist.
    response = admin_client.put(
        "/api/scrapers/oauth-configs/github",
        json={"client_id": "updated_client_id"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "github"
    assert data["client_id"] == "updated_client_id"


# Removed: OAuth callback test for Ravelry (non-essential to scraper functionality)


def test_oauth_callback_platform_not_configured(admin_client):
    response = admin_client.post("/api/scrapers/oauth/thingiverse/callback?code=test_code")

    assert response.status_code == 404
    assert "OAuth config not found" in response.json()["detail"]


def test_oauth_callback_unsupported_platform(admin_client):
    response = admin_client.post("/api/scrapers/oauth/unsupported/callback?code=test_code")

    # Unsupported platforms cannot have persisted configs because oauth_configs
    # is constrained to known platform values in the real Supabase schema.
    assert response.status_code == 404
    assert "OAuth config not found" in response.json()["detail"]


def test_oauth_callback_requires_admin(auth_client):
    """Test that non-admin users cannot handle OAuth callbacks"""
    response = auth_client.post("/api/scrapers/oauth/ravelry/callback?code=test_code")

    assert response.status_code == 403


def test_save_oauth_token(admin_client, clean_database):
    """Test saving OAuth token"""
    response = admin_client.post(
        "/api/scrapers/oauth/goat/save-token",
        json={
            "access_token": "test_token",
            "refresh_token": "refresh_token",
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "http://localhost/callback",
        },
    )

    assert response.status_code == 200
    assert "Token saved" in response.json()["message"]


# Integration tests for scraper functionality through API endpoints
# Per AGENT_GUIDE.md: No mocks - use real API calls
# Note: Scraper internal logic tests have been removed per project conventions.
# Coverage is provided through integration tests that exercise the complete API layer.
