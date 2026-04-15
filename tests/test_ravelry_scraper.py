"""Tests for Ravelry scraper"""

import pytest

from scrapers.ravelry import RavelryScraper

pytestmark = pytest.mark.integration


def test_create_product_dict_uses_pattern_attributes_for_tags():
    """pattern_attributes (not personal_attributes) should populate tags"""
    scraper = RavelryScraper(None, access_token="fake-token")

    pattern_data = {
        "id": 12345,
        "name": "Capitalist Mouse Fairy Fidget",
        "permalink": "capitalist-mouse-fairy-fidget",
        "notes_html": "",
        "craft": {"name": "Crochet"},
        "pattern_type": {"name": "Toys"},
        "pattern_categories": [],
        "pattern_attributes": [
            {"id": 1, "name": "Amigurumi", "permalink": "amigurumi"},
            {"id": 2, "name": "In The Round", "permalink": "in-the-round"},
            {"id": 3, "name": "Therapy Aid", "permalink": "therapy-aid"},
            {"id": 4, "name": "Written Pattern", "permalink": "written-pattern"},
        ],
        # personal_attributes should be ignored for tags
        "personal_attributes": [
            {"name": "favorited"},
            {"name": "in_library"},
            {"name": "queued"},
        ],
        "designer": {"name": "Test Designer"},
        "first_photo": None,
        "photos": [],
        "rating_average": 4.5,
        "rating_count": 10,
        "updated_at": None,
        "free": True,
    }

    result = scraper._create_product_dict(pattern_data)

    # pattern_attributes should be in tags
    assert "Amigurumi" in result["tags"]
    assert "In The Round" in result["tags"]
    assert "Therapy Aid" in result["tags"]
    assert "Written Pattern" in result["tags"]

    # personal_attributes should NOT appear as tags
    assert "favorited" not in result["tags"]
    assert "in_library" not in result["tags"]
    assert "queued" not in result["tags"]

    # external_data should store pattern_attributes, not personal_attributes
    assert "pattern_attributes" in result["external_data"]
    assert "personal_attributes" not in result["external_data"]
    assert len(result["external_data"]["pattern_attributes"]) == 4


def test_create_product_dict_uses_pattern_categories_for_tags():
    """pattern_categories (including parent categories) should populate tags"""
    scraper = RavelryScraper(None, access_token="fake-token")

    pattern_data = {
        "id": 12345,
        "name": "Stuffed Bunny",
        "permalink": "stuffed-bunny",
        "notes_html": "",
        "craft": {"name": "Crochet"},
        "pattern_type": None,
        "pattern_categories": [
            {
                "id": 340,
                "name": "Stuffed Animals",
                "permalink": "stuffed-animals",
                "parent": {"id": 339, "name": "Toys", "permalink": "toys"},
            }
        ],
        "pattern_attributes": [],
        "designer": None,
        "first_photo": None,
        "photos": [],
        "rating_average": None,
        "rating_count": 0,
        "updated_at": None,
        "free": True,
    }

    result = scraper._create_product_dict(pattern_data)

    # Both child and parent category names should appear in tags
    assert "Stuffed Animals" in result["tags"]
    assert "Toys" in result["tags"]

    # external_data should include pattern_categories
    assert "pattern_categories" in result["external_data"]
    assert len(result["external_data"]["pattern_categories"]) == 1


def test_create_product_dict_no_pattern_attributes():
    """Scraper should handle patterns with no pattern_attributes gracefully"""
    scraper = RavelryScraper(None, access_token="fake-token")

    pattern_data = {
        "id": 99,
        "name": "Simple Pattern",
        "permalink": "simple-pattern",
        "notes_html": "A simple pattern.",
        "craft": {"name": "Knitting"},
        "pattern_type": None,
        "pattern_categories": [],
        "pattern_attributes": [],
        "designer": None,
        "first_photo": None,
        "photos": [],
        "rating_average": None,
        "rating_count": 0,
        "updated_at": None,
        "free": False,
    }

    result = scraper._create_product_dict(pattern_data)

    assert result["name"] == "Simple Pattern"
    assert result["tags"] == []
    assert result["external_data"]["pattern_attributes"] == []
    assert result["external_data"]["pattern_categories"] == []
