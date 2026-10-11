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
        "knitting",  # craft defaults to knitting when Ravelry gives none
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
    assert "crochet" in source_product.tags
    assert "knitting" not in source_product.tags
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


def _client_with_responses(statuses_and_bodies, seen_auth):
    """httpx client whose Nth call returns the Nth (status, body); records Authorization."""
    import httpx

    calls = iter(statuses_and_bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        status, body = next(calls)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer old"}
    )


async def test_ravelry_adapter_refreshes_token_on_401_and_retries(monkeypatch):
    seen_auth: list = []
    client = _client_with_responses(
        [(401, {}), (200, {"patterns": [{"id": 1}]})], seen_auth
    )
    adapter = RavelrySourceAdapter(supabase_client=None, access_token="old", client=client)

    async def fake_refresh():
        adapter.client.headers["Authorization"] = "Bearer new"
        return True

    monkeypatch.setattr(adapter, "_refresh_access_token", fake_refresh)

    patterns, _ = await adapter._search_patterns("adaptive", 1)

    assert patterns == [{"id": 1}]
    assert seen_auth == ["Bearer old", "Bearer new"]


async def test_ravelry_adapter_raises_when_token_cannot_be_refreshed(monkeypatch):
    from scrapers.core.ravelry_adapter import RavelryAuthError

    seen_auth: list = []
    client = _client_with_responses([(401, {})], seen_auth)
    adapter = RavelrySourceAdapter(supabase_client=None, access_token="old", client=client)

    async def no_refresh():
        return False

    monkeypatch.setattr(adapter, "_refresh_access_token", no_refresh)

    with pytest.raises(RavelryAuthError):
        await adapter._search_patterns("adaptive", 1)


async def test_ravelry_adapter_refresh_stores_new_tokens(monkeypatch):
    import httpx

    class _Table:
        def __init__(self, store):
            self.store = store
            self._update = None

        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def limit(self, *_a):
            return self

        def update(self, payload):
            self._update = payload
            return self

        def execute(self):
            if self._update is not None:
                self.store["updated"] = self._update
                return type("R", (), {"data": []})()
            return type(
                "R",
                (),
                {
                    "data": [
                        {
                            "client_id": "id",
                            "client_secret": "secret",
                            "refresh_token": "old-refresh",
                            "redirect_uri": "http://localhost/cb",
                        }
                    ]
                },
            )()

    store: dict = {}

    class _Supabase:
        def table(self, _name):
            return _Table(store)

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"refresh_token=old-refresh" in request.content
        return httpx.Response(
            200,
            json={"access_token": "fresh", "refresh_token": "next-refresh", "expires_in": 3600},
        )

    real_client = httpx.AsyncClient
    # The adapter calls httpx.AsyncClient() for the refresh request; patch that class.
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: real_client(transport=httpx.MockTransport(handler)),
    )

    adapter = RavelrySourceAdapter(
        supabase_client=_Supabase(), access_token="old", client=real_client()
    )

    assert await adapter._refresh_access_token() is True
    assert store["updated"]["access_token"] == "fresh"
    assert store["updated"]["refresh_token"] == "next-refresh"
    assert "token_expires_at" in store["updated"]
    assert adapter.client.headers["Authorization"] == "Bearer fresh"
