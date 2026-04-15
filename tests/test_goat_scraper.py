"""
Test for LibraryThing scraper
Tests URL extraction, API interaction, and product creation
"""

import pytest

from scrapers.goat import GOATScraper

pytestmark = pytest.mark.integration


def test_extract_work_id():
    """Test work ID extraction from various LibraryThing URLs"""
    scraper = GOATScraper(None)

    # Test full work + edition URL
    assert (
        scraper._extract_work_id("https://www.librarything.com/work/35356138/book/302275636")
        == "35356138"
    )

    # Test work-only URL
    assert scraper._extract_work_id("https://www.librarything.com/work/35356138") == "35356138"

    # Test with different domain format
    assert scraper._extract_work_id("http://librarything.com/work/12345") == "12345"

    # Test invalid URL
    assert scraper._extract_work_id("https://www.librarything.com/user/someuser") is None


def test_supports_url():
    """Test URL support checking"""
    scraper = GOATScraper(None)

    assert scraper.supports_url("https://www.librarything.com/work/35356138")
    assert scraper.supports_url("http://librarything.com/work/12345/book/999")
    assert not scraper.supports_url("https://www.ravelry.com/patterns/library/test")
    assert not scraper.supports_url("https://www.github.com/user/repo")


def test_get_source_name():
    """Test source name"""
    scraper = GOATScraper(None)
    assert scraper.get_source_name() == "goat"


def test_parse_xml_response_valid():
    """Test parsing valid XML response from LibraryThing API"""
    scraper = GOATScraper(None)

    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ltml:response xmlns:ltml="http://www.librarything.com/services/" status="ok">
        <work>
            <id>35356138</id>
            <title>The Curious Garden</title>
            <author>
                <name>Peter Brown</name>
            </author>
            <description>A story about a boy who finds a secret garden.</description>
            <language>English</language>
            <publicationyear>2009</publicationyear>
            <cover>
                <id>123456</id>
            </cover>
            <populartags>
                <tag>
                    <name>children</name>
                </tag>
                <tag>
                    <name>nature</name>
                </tag>
                <tag>
                    <name>gardens</name>
                </tag>
            </populartags>
        </work>
    </ltml:response>"""

    result = scraper._parse_xml_response(xml_response, "35356138")

    assert result is not None
    assert result["work_id"] == "35356138"
    assert result["title"] == "The Curious Garden"
    assert result["author"] == "Peter Brown"
    assert "A story about a boy" in result["description"]
    assert result["language"] == "English"
    assert result["publication_year"] == "2009"
    assert "https://covers.librarything.com/pics/123456l" == result["image_url"]
    assert len(result["tags"]) == 3
    assert "children" in result["tags"]


def test_parse_xml_response_error():
    """Test parsing error response from LibraryThing API"""
    scraper = GOATScraper(None)

    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ltml:response xmlns:ltml="http://www.librarything.com/services/" status="error">
        <error>
            <message>Work not found</message>
        </error>
    </ltml:response>"""

    result = scraper._parse_xml_response(xml_response, "invalid")
    assert result is None


def test_parse_xml_response_minimal():
    """Test parsing minimal XML response (missing optional fields)"""
    scraper = GOATScraper(None)

    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <ltml:response xmlns:ltml="http://www.librarything.com/services/" status="ok">
        <work>
            <id>12345</id>
            <title>Minimal Book</title>
        </work>
    </ltml:response>"""

    result = scraper._parse_xml_response(xml_response, "12345")

    assert result is not None
    assert result["work_id"] == "12345"
    assert result["title"] == "Minimal Book"
    assert result["author"] is None
    assert result["description"] is None
    assert result["image_url"] is None


def test_create_product_dict():
    """Test converting LibraryThing work data to product dict"""
    scraper = GOATScraper(None)

    work_data = {
        "work_id": "35356138",
        "title": "The Curious Garden",
        "author": "Peter Brown",
        "description": "A beautiful story about discovering nature.",
        "image_url": "https://covers.librarything.com/pics/123456l",
        "tags": ["children", "nature"],
        "language": "English",
        "publication_year": "2009",
        "url": "https://www.librarything.com/work/35356138",
    }

    product_dict = scraper._create_product_dict(work_data)

    assert product_dict["name"] == "The Curious Garden"
    assert "Peter Brown" in product_dict["description"]
    assert product_dict["source"] == "GOAT"
    assert product_dict["type"] == "Book"
    assert product_dict["external_id"] == "35356138"
    assert "children" in product_dict["tags"]
    assert product_dict["image"] == "https://covers.librarything.com/pics/123456l"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
