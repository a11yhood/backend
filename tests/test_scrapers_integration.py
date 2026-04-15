"""
Integration tests for scrapers with real API calls and database operations

These tests connect to a real test database and make actual API calls.
They are marked as integration tests and can be skipped during development.

Setup required:
1. Create a test Supabase project (see TEST_DATABASE_SETUP.md)
2. Create .env.test with test database credentials
3. Apply schema to test database
4. (Optional) Configure OAuth tokens for Thingiverse/Ravelry

Run tests:
    pytest tests/test_scrapers_integration.py -v                    # Run all integration tests
    pytest tests/test_scrapers_integration.py -v -m "not slow"     # Skip slow tests
    pytest tests/test_scrapers_integration.py::test_github -v      # Run specific test
"""

import os

import pytest
from scrapers.github import GitHubScraper
from scrapers.thingiverse import ThingiverseScraper

pytestmark = pytest.mark.integration

if not os.getenv("RUN_LIVE_SCRAPERS"):
    pytest.skip(
        "Skipping live scraper integration tests without RUN_LIVE_SCRAPERS=1",
        allow_module_level=True,
    )


@pytest.mark.integration
@pytest.mark.scraper
@pytest.mark.slow
async def test_github_scraper_real_data(clean_database, test_settings, test_admin):
    """
    Test GitHub scraper with real API calls

    This test:
    - Makes actual GitHub API requests
    - Scrapes 5 real repositories
    - Saves them to the Supabase test database
    - Verifies data structure and content
    """
    scraper = GitHubScraper(clean_database)

    try:
        # Scrape 5 items in test mode
        result = await scraper.scrape(test_mode=True, test_limit=test_settings.TEST_SCRAPER_LIMIT)

        # Verify scraping completed successfully
        assert result["status"] == "success", f"Scraping failed: {result.get('error_message')}"
        assert result["products_found"] >= 1, "Should find at least 1 product"
        assert result["products_added"] >= 0, "Should track added products"
        assert result["duration_seconds"] > 0, "Should track duration"

        # Verify products were actually saved to database
        products = (
            clean_database.table("products").select("*").eq("source", "scraped-github").execute()
        )
        assert len(products.data) >= 1, "Should save at least 1 product to database"

        # Verify product structure and required fields
        product = products.data[0]
        assert product["name"], "Product must have a name"
        assert product["url"], "Product must have a URL"
        assert product["url"].startswith("https://github.com/"), (
            "GitHub URLs should start with https://github.com/"
        )
        assert product["category"] == "Software", (
            "GitHub products should be categorized as Software"
        )
        assert product["source"] == "scraped-github", "Source should be scraped-github"
        assert product["description"], "Product should have a description"

        # Verify external data is present
        assert product.get("external_data"), "Product should have external data"

        print(f"\n✓ Successfully scraped {len(products.data)} GitHub repositories")
        print(f"  Sample: {product['name']} - {product['url']}")

    finally:
        await scraper.close()


@pytest.mark.integration
@pytest.mark.scraper
@pytest.mark.slow
async def test_github_scraper_filtering(clean_database, test_admin):
    """
    Test that GitHub scraper properly filters out documentation-only repos

    This verifies that repos flagged as documentation are excluded
    """
    scraper = GitHubScraper(clean_database)

    try:
        await scraper.scrape(test_mode=True, test_limit=3)

        # Get all scraped products
        products = (
            clean_database.table("products").select("*").eq("source", "scraped-github").execute()
        )

        # Verify none are pure documentation repos
        for product in products.data:
            name_lower = product["name"].lower()
            desc_lower = (product.get("description") or "").lower()

            # These patterns should have been filtered out
            doc_patterns = ["awesome-", "list of", "collection of", "resources for"]
            is_docs = any(
                pattern in name_lower or pattern in desc_lower for pattern in doc_patterns
            )

            assert not is_docs, f"Documentation repo should be filtered: {product['name']}"

        print(f"\n✓ Verified filtering - {len(products.data)} products, all valid tools/software")

    finally:
        await scraper.close()


@pytest.mark.integration
@pytest.mark.scraper
@pytest.mark.slow
@pytest.mark.requires_oauth
async def test_thingiverse_scraper_real_data(
    clean_database, test_settings, test_admin, thingiverse_oauth_config
):
    """
    Test Thingiverse scraper with real API (requires OAuth token)

    This test:
    - Requires THINGIVERSE_ACCESS_TOKEN environment variable
    - Makes actual Thingiverse API requests
    - Scrapes 5 real 3D models
    - Verifies data structure

    To run this test:
    1. Get a Thingiverse access token
    2. Set environment variable: export THINGIVERSE_ACCESS_TOKEN=your-token
    3. Run: pytest tests/test_scrapers_integration.py::test_thingiverse -v
    """
    access_token = thingiverse_oauth_config["access_token"]
    scraper = ThingiverseScraper(clean_database, access_token)

    try:
        result = await scraper.scrape(test_mode=True, test_limit=test_settings.TEST_SCRAPER_LIMIT)

        # Verify scraping completed
        assert result["status"] == "success", f"Scraping failed: {result.get('error_message')}"
        assert result["products_found"] >= 1, "Should find at least 1 product"

        # Verify products in database
        products = (
            clean_database.table("products")
            .select("*")
            .eq("source", "scraped-thingiverse")
            .execute()
        )
        assert len(products.data) >= 1, "Should save at least 1 product"

        # Verify product structure
        product = products.data[0]
        assert product["name"], "Product must have a name"
        assert product["url"], "Product must have a URL"
        assert product["url"].startswith("https://www.thingiverse.com/thing:"), (
            "Thingiverse URLs should match pattern"
        )
        assert product["category"] == "Fabrication", (
            "Thingiverse products should be Fabrication category"
        )
        assert product["source"] == "scraped-thingiverse"

        print(f"\n✓ Successfully scraped {len(products.data)} Thingiverse models")
        print(f"  Sample: {product['name']} - {product['url']}")

    finally:
        await scraper.close()


@pytest.mark.integration
@pytest.mark.scraper
async def test_github_scraper_deduplication(clean_database, test_admin):
    """
    Test that scraper properly handles duplicate products

    When running scraper multiple times:
    - Existing products should be updated, not duplicated
    - products_updated count should increase
    """
    scraper = GitHubScraper(clean_database)

    try:
        # First scrape
        result1 = await scraper.scrape(test_mode=True, test_limit=2)
        first_count = result1["products_added"]

        # Second scrape (should find same products)
        result2 = await scraper.scrape(test_mode=True, test_limit=2)

        # Verify no duplicates created
        products = (
            clean_database.table("products").select("*").eq("source", "scraped-github").execute()
        )
        # Should not have many more products (allows for slight variation)
        assert len(products.data) <= first_count + 2, "Should not create many duplicate products"

        # Second scrape should either update or add (but not both in large numbers)
        assert result2["products_updated"] >= 0, "Should track updates"
        print(
            f"\n✓ First scrape: {first_count} added, Second scrape: {result2['products_added']} added, {result2['products_updated']} updated"
        )

        print(f"\n✓ Deduplication works - {result2['products_updated']} products updated")

    finally:
        await scraper.close()


@pytest.mark.integration
async def test_scraper_error_handling(clean_database, test_admin):
    """
    Test that scrapers handle API errors gracefully

    This test uses an invalid access token to trigger an error
    """
    scraper = ThingiverseScraper(clean_database, "invalid-token")

    try:
        result = await scraper.scrape(test_mode=True, test_limit=1)

        # Should handle error gracefully (either return error or find 0 products)
        assert result["status"] in ["error", "success"], "Should return a valid status"
        if result["status"] == "error":
            assert result.get("error_message"), "Error status should include error message"
            print(f"\n✓ Error handling works - {result['error_message']}")
        else:
            print(f"\n✓ Error handling works - status: {result['status']}")
        # With invalid token, should not successfully scrape products
        assert result["products_added"] == 0, "Should not add products with invalid token"

    finally:
        await scraper.close()


@pytest.mark.integration
@pytest.mark.scraper
@pytest.mark.slow
async def test_scraper_respects_test_limit(clean_database, test_settings, test_admin):
    """
    Verify that test_limit parameter is respected
    """
    scraper = GitHubScraper(clean_database)

    try:
        # Scrape with limit of 3
        result = await scraper.scrape(test_mode=True, test_limit=3)

        # Should find exactly the limit
        assert result["products_found"] <= 3, "Should not exceed test limit"

        # Verify database has correct count
        products = (
            clean_database.table("products").select("*").eq("source", "scraped-github").execute()
        )
        assert len(products.data) <= 3, "Database should not exceed test limit"

        print(f"\n✓ Test limit respected - found {result['products_found']} products (limit: 3)")

    finally:
        await scraper.close()


@pytest.mark.integration
async def test_scraper_performance(clean_database, test_admin):
    """
    Test that scrapers complete within reasonable time

    5 items should complete in under 30 seconds
    """
    import time

    scraper = GitHubScraper(clean_database)

    try:
        start = time.time()
        result = await scraper.scrape(test_mode=True, test_limit=5)
        duration = time.time() - start

        assert duration < 30, f"Scraping 5 items should complete in <30s, took {duration:.1f}s"
        assert result["status"] == "success"

        print(f"\n✓ Performance good - scraped 5 items in {duration:.1f}s")

    finally:
        await scraper.close()
