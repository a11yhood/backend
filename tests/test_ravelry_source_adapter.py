import pytest

pytest.importorskip("scrapers.core.ravelry_adapter")

from scrapers.core.contracts import ScrapeMode, ScrapeRunContext
from scrapers.core.ravelry_adapter import RavelrySourceAdapter


def test_ravelry_source_adapter_supports_url():
    adapter = RavelrySourceAdapter(supabase_client=None)

    assert adapter.supports_url("https://www.ravelry.com/patterns/library/some-pattern")
    assert not adapter.supports_url("https://example.com/patterns/library/some-pattern")


def test_ravelry_source_adapter_generate_tags_uses_pattern_fields_only():
    adapter = RavelrySourceAdapter(supabase_client=None)

    tags = adapter.generate_tags(
        {
            "pattern_type": {"name": "Toys"},
            "pattern_categories": [
                {
                    "name": "Stuffed Animals",
                    "parent": {"name": "Toys"},
                }
            ],
            "pattern_attributes": [
                {"name": "Amigurumi"},
                {"name": "Written Pattern"},
                {"name": "Amigurumi"},
            ],
            "designer": {"name": "Jane Doe"},
            "personal_attributes": [{"name": "favorited"}],
        },
        {},
    )

    assert tags == [
        "Toys",
        "Stuffed Animals",
        "Amigurumi",
        "Written Pattern",
        "Designer: Jane Doe",
    ]
    assert "favorited" not in tags


def test_ravelry_source_adapter_maps_pattern_to_source_product():
    adapter = RavelrySourceAdapter(supabase_client=None)
    context = ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT)

    source_product = adapter.map_to_source_product(
        {
            "id": 12345,
            "name": "Stuffed Bunny",
            "permalink": "stuffed-bunny",
            "notes_html": "A cute bunny pattern",
            "craft": {"name": "Crochet"},
            "pattern_type": {"name": "Toys"},
            "pattern_categories": [{"name": "Stuffed Animals", "parent": {"name": "Toys"}}],
            "pattern_attributes": [{"name": "Amigurumi"}],
            "designer": {"name": "Jane Doe"},
            "first_photo": {"medium_url": "https://images.example/bunny.png"},
            "rating_average": 4.6,
            "rating_count": 42,
            "updated_at": "2019/08/29 20:22:16 -0400",
            "free": True,
            "_matched_pa_category": "therapy-aid",
        },
        context,
    )

    assert source_product.source == "ravelry"
    assert source_product.external_id == "12345"
    assert source_product.source_url == "https://www.ravelry.com/patterns/library/stuffed-bunny"
    assert source_product.name == "Stuffed Bunny"
    assert source_product.type == "Crochet"
    assert source_product.image_url == "https://images.example/bunny.png"
    assert source_product.image_alt == "Stuffed Bunny image (ALT text missing on source)"
    assert source_product.source_rating == 4.6
    assert source_product.source_rating_count == 42
    assert source_product.matched_search_terms == ["therapy-aid"]
    assert source_product.source_last_updated is not None
    assert "Amigurumi" in source_product.tags


async def test_ravelry_source_adapter_enumerate_candidates_full_depth(monkeypatch):
    adapter = RavelrySourceAdapter(supabase_client=None)
    adapter.PA_CATEGORIES = ["cat-a", "cat-b"]

    async def fake_search(pa_category: str, page: int):
        if pa_category == "cat-a" and page == 1:
            return [{"id": 1}, {"id": 2}], True
        if pa_category == "cat-a" and page == 2:
            return [{"id": 3}], False
        if pa_category == "cat-b" and page == 1:
            return [{"id": 4}], False
        return [], False

    monkeypatch.setattr(adapter, "_search_patterns", fake_search)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE)
    results = await adapter.enumerate_candidates(context)

    assert [item["id"] for item in results] == [1, 2, 3, 4]
    assert results[0]["_matched_pa_category"] == "cat-a"
    assert results[3]["_matched_pa_category"] == "cat-b"


async def test_ravelry_source_adapter_enumerate_candidates_respects_max_products(monkeypatch):
    adapter = RavelrySourceAdapter(supabase_client=None)
    adapter.PA_CATEGORIES = ["cat-a", "cat-b"]

    async def fake_search(pa_category: str, page: int):
        if pa_category == "cat-a" and page == 1:
            return [{"id": 1}, {"id": 2}, {"id": 3}], True
        if pa_category == "cat-a" and page == 2:
            return [{"id": 4}], False
        if pa_category == "cat-b" and page == 1:
            return [{"id": 5}], False
        return [], False

    monkeypatch.setattr(adapter, "_search_patterns", fake_search)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE_TEST_N, max_products=3)
    results = await adapter.enumerate_candidates(context)

    assert [item["id"] for item in results] == [1, 2, 3]


async def test_ravelry_source_adapter_fetch_one_carries_matched_category(monkeypatch):
    adapter = RavelrySourceAdapter(supabase_client=None)

    async def fake_details(pattern_id: int | str):
        assert str(pattern_id) == "99"
        return {
            "id": 99,
            "name": "Returned Pattern",
            "permalink": "returned-pattern",
        }

    monkeypatch.setattr(adapter, "_fetch_pattern_details", fake_details)

    raw = await adapter.fetch_one({"id": 99, "_matched_pa_category": "adaptive"}, ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT))

    assert raw is not None
    assert raw["_matched_pa_category"] == "adaptive"
