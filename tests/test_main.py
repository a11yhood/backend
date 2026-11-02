"""Test basic API functionality"""

import pytest

pytestmark = pytest.mark.functional


def test_root_endpoint(client):
    """Test root endpoint returns expected response"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "a11yhood API"


def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "mode" in data
    assert data["mode"] in ["development", "production"]
    assert "test_mode" in data
    assert "database" in data


def test_health_endpoint_reports_version(unit_client, monkeypatch):
    for name in ("GIT_SHA", "COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"):
        monkeypatch.delenv(name, raising=False)

    data = unit_client.get("/health").json()

    assert data["version"] == unit_client.get("/").json()["version"]
    assert "git_sha" not in data


def test_health_endpoint_reports_git_sha_when_set(unit_client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")

    assert unit_client.get("/health").json()["git_sha"] == "abc1234"


def test_health_endpoint_reports_connected_when_db_reachable(client):
    """Health check should actually probe the database, not just check config."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
