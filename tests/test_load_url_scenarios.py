"""Scenario coverage for public load-url product inquiry flow."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from scrapers.core.contracts import SourceScrapedProduct
from services.image_references import get_or_create_image_id

pytestmark = pytest.mark.integration


def _ensure_github_supported(db) -> None:
    existing = db.table("supported_sources").select("domain").eq("domain", "github.com").execute()
    if existing.data:
        return
    db.table("supported_sources").insert({"domain": "github.com", "name": "Github"}).execute()


def test_load_url_creates_product_when_missing(client, clean_database, monkeypatch):
    """When product is missing, load-url should fetch via adapter and create it."""
    from routers import scrapers as scraper_router

    _ensure_github_supported(clean_database)

    class FakeGitHubAdapter:
        def __init__(self, db, access_token=None):
            self.closed = False

        async def fetch_one(self, candidate, context):
            return {
                "source_url": candidate["source_url"],
                "external_id": "owner/repo",
                "name": "Adaptive Repo",
                "description": "Adapter-fetched description",
            }

        def map_to_source_product(self, raw, context):
            now = datetime.now(UTC).isoformat()
            return SourceScrapedProduct(
                source="Github",
                external_id=raw["external_id"],
                source_url=raw["source_url"],
                name=raw["name"],
                description=raw["description"],
                source_last_updated=now,
                matched_search_terms=["accessibility"],
                tags=["Assistive Tech"],
                image_url="https://example.com/adaptive-repo.png",
                image_alt="Adaptive Repo preview",
                source_rating=4.8,
                source_rating_count=12,
                external_data={"stars": 120},
                fetched_at=now,
                scrape_mode="single_product",
            )

        async def close(self):
            self.closed = True

    monkeypatch.setattr(scraper_router, "GitHubSourceAdapter", FakeGitHubAdapter)

    response = client.post(
        "/api/scrapers/load-url",
        json={"url": "https://github.com/owner/repo?tab=readme"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["source"] == "scraped"
    assert body["product"]["source_url"] == "https://github.com/owner/repo"
    assert body["product"]["name"] == "Adaptive Repo"


def test_load_url_returns_existing_product_without_refresh_if_complete(
    client, clean_database, monkeypatch
):
    """When product exists and has a valid image URL, load-url should return database record only."""
    from routers import scrapers as scraper_router

    _ensure_github_supported(clean_database)

    source_url = "https://github.com/existing/complete"
    image_id = get_or_create_image_id(clean_database, "https://example.com/existing-complete.jpg")
    insert_response = (
        clean_database.table("products")
        .insert(
            {
                "name": "Existing Complete",
                "description": "Already complete",
                "source_url": source_url,
                "source": "Github",
                "slug": f"existing-complete-{uuid4().hex[:8]}",
                "image_id": image_id,
            }
        )
        .execute()
    )
    product_id = insert_response.data[0]["id"]

    # Simulate a valid externally displayable URL so no refresh path is triggered.
    monkeypatch.setattr(
        scraper_router,
        "resolve_image_value",
        lambda db, img_id: "https://example.com/existing-complete.jpg",
    )

    class ShouldNotBeCalledAdapter:
        def __init__(self, db, access_token=None):
            raise AssertionError("Adapter should not be created for complete existing product")

    monkeypatch.setattr(scraper_router, "GitHubSourceAdapter", ShouldNotBeCalledAdapter)

    response = client.post("/api/scrapers/load-url", json={"url": "https://github.com/existing/complete"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["source"] == "database"
    assert body["product"]["id"] == product_id


def test_load_url_refreshes_missing_image_info_for_existing_product(
    client, clean_database, monkeypatch
):
    """When product exists but image info is missing, load-url should refresh image fields."""
    from routers import scrapers as scraper_router

    _ensure_github_supported(clean_database)

    source_url = "https://github.com/existing/missing-image"
    insert_response = (
        clean_database.table("products")
        .insert(
            {
                "name": "Existing Missing",
                "description": "Missing image metadata",
                "source_url": source_url,
                "source": "Github",
                "slug": f"existing-missing-{uuid4().hex[:8]}",
                "image_id": None,
                "image_alt": None,
            }
        )
        .execute()
    )
    product_id = insert_response.data[0]["id"]

    calls = {"fetch_one": 0}

    class RefreshingGitHubAdapter:
        def __init__(self, db, access_token=None):
            self.closed = False

        async def fetch_one(self, candidate, context):
            calls["fetch_one"] += 1
            return {
                "source_url": candidate["source_url"],
                "external_id": "existing/missing-image",
                "name": "Existing Missing",
                "description": "Filled via refresh",
            }

        def map_to_source_product(self, raw, context):
            now = datetime.now(UTC).isoformat()
            return SourceScrapedProduct(
                source="Github",
                external_id=raw["external_id"],
                source_url=raw["source_url"],
                name=raw["name"],
                description=raw["description"],
                source_last_updated=now,
                matched_search_terms=[],
                tags=[],
                image_url="https://example.com/refreshed-image.png",
                image_alt="Refreshed alt text",
                source_rating=4.0,
                source_rating_count=5,
                external_data={},
                fetched_at=now,
                scrape_mode="single_product",
            )

        async def close(self):
            self.closed = True

    monkeypatch.setattr(scraper_router, "GitHubSourceAdapter", RefreshingGitHubAdapter)

    response = client.post("/api/scrapers/load-url", json={"url": source_url})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["source"] == "database"
    assert calls["fetch_one"] == 1

    refreshed = (
        clean_database.table("products")
        .select("id,image_id,image_alt")
        .eq("id", product_id)
        .limit(1)
        .execute()
    )
    assert refreshed.data
    assert refreshed.data[0]["image_id"] is not None
    assert refreshed.data[0]["image_alt"] == "Refreshed alt text"
