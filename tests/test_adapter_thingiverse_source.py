from scrapers.core import ScrapeMode, ScrapeRunContext, ThingiverseSourceAdapter


def test_thingiverse_source_adapter_supports_url():
    adapter = ThingiverseSourceAdapter(supabase_client=None)

    assert adapter.supports_url("https://www.thingiverse.com/thing:12345")
    assert not adapter.supports_url("https://example.com/thing:12345")


def test_thingiverse_source_adapter_maps_thing_to_source_product():
    adapter = ThingiverseSourceAdapter(supabase_client=None)
    context = ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT)

    source_product = adapter.map_to_source_product(
        {
            "id": 991,
            "name": "Adaptive Cup Holder",
            "description": "Cup holder for wheelchair rails",
            "public_url": "https://www.thingiverse.com/thing:991?utm_source=test",
            "make_count": 120,
            "like_count": 15,
            "favorite_count": 8,
            "tags": [{"name": "assistive"}, {"name": "mobility"}, {"name": "assistive"}],
            "categories": [{"name": "Tools"}, {"name": "Accessibility"}],
            "default_image": {"url": "https://cdn.thingiverse.com/image.png"},
            "modified": "2026-04-16T12:00:00Z",
            "_matched_search_term": "adaptive+tool",
        },
        context,
    )

    assert source_product.source == "thingiverse"
    assert source_product.external_id == "991"
    assert source_product.source_url == "https://www.thingiverse.com/thing:991"
    assert source_product.name == "Adaptive Cup Holder"
    assert "fabrication" in source_product.tags
    assert source_product.image_url == "https://cdn.thingiverse.com/image.png"
    assert source_product.image_alt == "Adaptive Cup Holder image (ALT text missing on source)"
    assert source_product.source_rating is not None
    assert source_product.source_rating_count == 120
    assert source_product.matched_search_terms == ["adaptive+tool"]
    assert source_product.tags == ["fabrication", "assistive", "mobility", "Tools", "Accessibility"]


def test_thingiverse_source_adapter_map_makes_to_source_rating_anchors():
    assert ThingiverseSourceAdapter.map_makes_to_source_rating(0) is None
    assert ThingiverseSourceAdapter.map_makes_to_source_rating(1) == 1.0
    assert ThingiverseSourceAdapter.map_makes_to_source_rating(10) == 2.0
    assert ThingiverseSourceAdapter.map_makes_to_source_rating(100) == 3.0
    assert ThingiverseSourceAdapter.map_makes_to_source_rating(1000) == 4.0


def test_thingiverse_source_adapter_extract_image_url_skips_non_images():
    adapter = ThingiverseSourceAdapter(supabase_client=None)

    image = adapter._extract_image_url(
        {
            "default_image": {"url": "https://cdn.thingiverse.com/model.stl"},
            "thumbnail": "https://cdn.thingiverse.com/thumb.stl",
            "images": [
                {
                    "sizes": [
                        {"url": "https://cdn.thingiverse.com/small.stl"},
                        {"url": "https://cdn.thingiverse.com/preview.png"},
                    ]
                }
            ],
        }
    )

    assert image == "https://cdn.thingiverse.com/preview.png"


async def test_thingiverse_source_adapter_enumerate_candidates_full_depth(monkeypatch):
    adapter = ThingiverseSourceAdapter(supabase_client=None)
    adapter.SEARCH_TERMS = ["term-a", "term-b"]

    async def fake_fetch(term: str, page: int, per_page: int):
        if term == "term-a" and page == 1:
            return [{"id": 1}, {"id": 2}], True
        if term == "term-a" and page == 2:
            return [{"id": 3}], False
        if term == "term-b" and page == 1:
            return [{"id": 4}], False
        return [], False

    monkeypatch.setattr(adapter, "_fetch_things_page", fake_fetch)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE)
    results = await adapter.enumerate_candidates(context)

    assert [item["id"] for item in results] == [1, 2, 3, 4]
    assert results[0]["_matched_search_term"] == "term-a"
    assert results[3]["_matched_search_term"] == "term-b"


async def test_thingiverse_source_adapter_enumerate_candidates_respects_max_products(monkeypatch):
    adapter = ThingiverseSourceAdapter(supabase_client=None)
    adapter.SEARCH_TERMS = ["term-a", "term-b"]

    async def fake_fetch(term: str, page: int, per_page: int):
        if term == "term-a" and page == 1:
            return [{"id": 1}, {"id": 2}, {"id": 3}], True
        if term == "term-a" and page == 2:
            return [{"id": 4}], False
        if term == "term-b" and page == 1:
            return [{"id": 5}], False
        return [], False

    monkeypatch.setattr(adapter, "_fetch_things_page", fake_fetch)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE_TEST_N, max_products=3)
    results = await adapter.enumerate_candidates(context)

    assert [item["id"] for item in results] == [1, 2, 3]


async def test_thingiverse_source_adapter_fetch_one_carries_matched_term(monkeypatch):
    adapter = ThingiverseSourceAdapter(supabase_client=None)

    async def fake_details(thing_id: str):
        assert thing_id == "77"
        return {
            "id": 77,
            "name": "Adaptive Handle",
            "public_url": "https://www.thingiverse.com/thing:77",
        }

    monkeypatch.setattr(adapter, "_fetch_thing_details", fake_details)

    raw = await adapter.fetch_one(
        {"source_url": "https://www.thingiverse.com/thing:77", "_matched_search_term": "adaptive+tool"},
        ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT),
    )

    assert raw is not None
    assert raw["_matched_search_term"] == "adaptive+tool"
