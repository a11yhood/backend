"""Scraper implementations for different platforms"""

from .base_scraper import BaseScraper, ScraperUtilities
from .github import GitHubScraper
from .goat import GOATScraper
from .ravelry import RavelryScraper
from .thingiverse import ThingiverseScraper

__all__ = [
    "BaseScraper",
    "ScraperUtilities",
    "GitHubScraper",
    "ThingiverseScraper",
    "RavelryScraper",
    "GOATScraper",
]
