"""
Integration coverage for supported source validation and source-domain request lifecycle.
These tests use the real database adapter (Supabase test instance) without mocks.
"""

import pytest

pytestmark = pytest.mark.integration


def test_load_url_blocks_unsupported_domain(client):
    """Public load-url should reject domains not in supported_sources."""
    response = client.post("/api/scrapers/load-url", json={"url": "https://example.com/widget"})

    assert response.status_code == 400  # Endpoint returns 400 for unsupported domain
    # The error will be in the detail or validation error format


def test_source_domain_request_approval_adds_source_and_allows_validation(
    client, test_user, test_admin, sqlite_db, auth_headers
):
    """Approving a source-domain request should auto-add the domain and allow validation to pass."""
    reason = "Domain: example.com\nURL: https://example.com/widget"

    create = client.post(
        "/api/requests/",
        json={"type": "source-domain", "reason": reason},
        headers=auth_headers(test_user),
    )
    assert create.status_code == 201
    request_id = create.json()["id"]

    approve = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )
    assert approve.status_code == 200

    sources = (
        sqlite_db.table("supported_sources").select("domain").eq("domain", "example.com").execute()
    )
    assert len(sources.data) == 1

    load = client.post("/api/scrapers/load-url", json={"url": "https://example.com/widget"})
    assert load.status_code == 200
    load_body = load.json()
    assert load_body.get("success") is False
    assert "not supported by any scraper" in load_body.get("message", "").lower()
