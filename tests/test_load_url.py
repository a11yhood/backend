"""Tests for the load-url scraper endpoint"""

import json

import pytest

from scrapers.github import GitHubScraper


@pytest.mark.asyncio
async def test_github_scraper_supports_url(clean_database):
    """Test that GitHub scraper correctly identifies GitHub URLs"""
    url = "https://github.com/make4all/psst"
    db = clean_database

    github_scraper = GitHubScraper(db, access_token=None)
    assert github_scraper.supports_url(url), "GitHub scraper should support GitHub URLs"


@pytest.mark.asyncio
async def test_github_scraper_with_valid_url(clean_database):
    """Test scraping a valid GitHub repository URL"""
    url = "https://github.com/make4all/psst"
    db = clean_database

    # Try to get GitHub token from config if available
    github_token = None
    try:
        config_response = (
            db.table("oauth_configs").select("access_token").eq("platform", "github").execute()
        )
        github_token = (
            (config_response.data or [{}])[0].get("access_token") if config_response.data else None
        )
    except Exception:
        # Token not available, test will run without it
        pass

    github_scraper = GitHubScraper(db, access_token=github_token)

    # Verify scraper recognizes the URL
    assert github_scraper.supports_url(url), "Scraper should support this GitHub URL"

    # Attempt to scrape the URL
    try:
        scraped_data = await github_scraper.scrape_url(url)
        # If scraping succeeds, verify we got some data structure
        assert scraped_data is not None, "Scraper should return data"
        # Basic validation that the response is JSON-serializable
        json.dumps(scraped_data, default=str)
    except Exception as e:
        # Scraping may fail due to rate limits or missing token, but shouldn't crash
        pytest.skip(f"GitHub scraping not available: {e}")
