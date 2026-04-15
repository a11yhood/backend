"""Test basic API functionality"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


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
