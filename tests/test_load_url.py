"""Tests for the load-url scraper endpoint"""

import json

import pytest

from scrapers.github import GitHubScraper


@pytest.mark.unit
async def test_github_scraper_supports_url():
    """Test that GitHub scraper correctly identifies GitHub URLs"""
    url = "https://github.com/make4all/psst"

    github_scraper = GitHubScraper(None, access_token=None)
    try:
        assert github_scraper.supports_url(url), "GitHub scraper should support GitHub URLs"
    finally:
        await github_scraper.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_oauth
async def test_github_scraper_with_valid_url(clean_database):
    """Test scraping a valid GitHub repository URL"""
    url = "https://github.com/make4all/psst"
    db = clean_database

    # Try to get GitHub token from config if available
    config_response = db.table("oauth_configs").select("access_token").eq("platform", "github").execute()
    github_token = (config_response.data or [{}])[0].get("access_token") if config_response.data else None
    if not github_token:
        pytest.skip("GitHub scraping test requires a configured github access token")

    github_scraper = GitHubScraper(db, access_token=github_token)

    # Verify scraper recognizes the URL
    assert github_scraper.supports_url(url), "Scraper should support this GitHub URL"

    # Attempt to scrape the URL and fail on unexpected runtime errors.
    scraped_data = await github_scraper.scrape_url(url)
    assert scraped_data is not None, "Scraper should return data"
    # Basic validation that the response is JSON-serializable
    json.dumps(scraped_data, default=str)
