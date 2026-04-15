"""Tests for /api/dev/* endpoints.

Covers:
- Gating: endpoints return 404 outside TEST_MODE
- Admin-only access: non-admin users receive 403
- /api/dev/health-dev: public health check
- /api/dev/stats: returns dev configuration and row counts
- /api/dev/reset: clears tables and returns counts
- /api/dev/check-limits: reports over-limit tables
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_headers(test_admin):
    return {"Authorization": f"Bearer dev-token-{test_admin['id']}"}


def _user_headers(test_user):
    return {"Authorization": f"Bearer dev-token-{test_user['id']}"}


# ---------------------------------------------------------------------------
# Gating: dev endpoints are only available in TEST_MODE
# ---------------------------------------------------------------------------

def test_health_dev_available_in_test_mode(client):
    """health-dev returns 200 when TEST_MODE is active."""
    response = client.get("/api/dev/health-dev")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "dev"


def test_health_dev_unavailable_outside_test_mode(clean_database):
    """health-dev returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db
    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    with patch("routers.dev.load_settings_from_env") as mock_settings:
        mock_settings.return_value = MagicMock(TEST_MODE=False)
        response = test_client.get("/api/dev/health-dev")
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_stats_unavailable_outside_test_mode(clean_database, test_admin):
    """stats returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db
    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    with patch("routers.dev.load_settings_from_env") as mock_settings:
        mock_settings.return_value = MagicMock(TEST_MODE=False)
        response = test_client.get(
            "/api/dev/stats", headers=_admin_headers(test_admin)
        )
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_reset_unavailable_outside_test_mode(clean_database, test_admin):
    """reset returns 404 when TEST_MODE is false."""
    from main import app
    from services.database import get_db
    app.dependency_overrides[get_db] = lambda: clean_database
    test_client = TestClient(app)

    with patch("routers.dev.load_settings_from_env") as mock_settings:
        mock_settings.return_value = MagicMock(TEST_MODE=False)
        response = test_client.post(
            "/api/dev/reset", headers=_admin_headers(test_admin)
        )
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
    """reset returns status='reset' and cleared_tables counts."""
    response = client.post("/api/dev/reset", headers=_admin_headers(test_admin))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset"
    assert "cleared_tables" in data
    assert "total_rows_deleted" in data
    assert isinstance(data["total_rows_deleted"], int)


# ---------------------------------------------------------------------------
# /api/dev/check-limits
# ---------------------------------------------------------------------------

def test_check_limits_ok_when_within_limit(client, test_admin):
    """check-limits returns 200 when all tables are within the configured limit."""
    response = client.get("/api/dev/check-limits", headers=_admin_headers(test_admin))
    # After a clean seed the tables should be well under the 20-row default.
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_check_limits_returns_400_when_exceeded(client, test_admin):
    """check-limits returns 400 with details when any table exceeds the limit."""
    with patch("routers.dev.enforce_dev_row_limits") as mock_enforce:
        mock_enforce.side_effect = ValueError(
            "Dev row limits exceeded (max 20):\n  - products: 25/20"
        )
        response = client.get(
            "/api/dev/check-limits", headers=_admin_headers(test_admin)
        )
    assert response.status_code == 400
    assert "Dev row limits exceeded" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Automatic row limit enforcement via DatabaseAdapter
# ---------------------------------------------------------------------------

def test_insert_raises_when_table_at_limit(clean_database):
    """_RowLimitedTableBuilder raises ValueError on insert when table is at DEV_MODE_MAX_ROWS_PER_TABLE."""
    from database_adapter import _RowLimitedTableBuilder

    max_rows = clean_database.settings.DEV_MODE_MAX_ROWS_PER_TABLE
    mock_supabase = MagicMock()
    mock_count_resp = MagicMock()
    mock_count_resp.count = max_rows
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_count_resp

    mock_builder = MagicMock()
    wrapper = _RowLimitedTableBuilder(mock_builder, mock_supabase, "products", max_rows)

    with pytest.raises(ValueError, match="Dev row limit exceeded"):
        wrapper.insert({"name": "overflow"})
