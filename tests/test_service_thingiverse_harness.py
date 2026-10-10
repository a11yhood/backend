import os

from services.scrapers import ScraperService


class _Query:
    def __init__(self, data):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("Response", (), {"data": self._data})()


class _SupabaseStub:
    def table(self, _name):
        # Return no persisted scraper_search_terms so adapter defaults are used.
        return _Query([])


async def test_scrape_thingiverse_uses_core_harness(monkeypatch):
    monkeypatch.setenv("THINGIVERSE_USE_CORE_HARNESS", "1")
    service = ScraperService(_SupabaseStub())

    class FakeAdapter:
        def __init__(self, supabase_client, access_token=None):
            self.access_token = access_token
            self.SEARCH_TERMS = []

        async def enumerate_candidates(self, context):
            assert context.max_products == 2
            return [{"id": 1}, {"id": 2}]

        async def fetch_one(self, candidate, context):
            return {
                "id": candidate["id"],
                "name": f"Thing {candidate['id']}",
                "public_url": f"https://www.thingiverse.com/thing:{candidate['id']}",
            }

        async def close(self):
            return None

    class FakeLegacyThingiverseScraper:
        def __init__(self, supabase_client, access_token=None):
            self._seen = 0
            self.SEARCH_TERMS = []

        def get_source_name(self):
            return "thingiverse"

        async def _product_exists(self, url, external_id=None, source=None):
            self._seen += 1
            if self._seen == 2:
                return {"id": "existing-2"}
            return None

        async def _create_product(self, raw_data):
            return True

        async def _update_product(self, product_id, raw_data):
            return True

        async def close(self):
            return None

    monkeypatch.setattr("services.scrapers.ThingiverseSourceAdapter", FakeAdapter)
    monkeypatch.setattr("services.scrapers.ThingiverseScraper", FakeLegacyThingiverseScraper)

    result = await service.scrape_thingiverse(access_token="token", test_mode=True, test_limit=2)

    assert result["status"] == "success"
    assert result["products_found"] == 2
    assert result["products_added"] == 1
    assert result["products_updated"] == 1
    assert result["harness"] == "core"


async def test_scrape_thingiverse_uses_legacy_when_harness_disabled(monkeypatch):
    monkeypatch.setenv("THINGIVERSE_USE_CORE_HARNESS", "0")
    service = ScraperService(_SupabaseStub())

    class FakeLegacyThingiverseScraper:
        def __init__(self, supabase_client, access_token=None):
            self.SEARCH_TERMS = []

        async def scrape(self, test_mode=False, test_limit=5):
            return {
                "source": "Thingiverse",
                "products_found": 3,
                "products_added": 2,
                "products_updated": 1,
                "duration_seconds": 0.1,
                "status": "success",
            }

        async def close(self):
            return None

    monkeypatch.setattr("services.scrapers.ThingiverseScraper", FakeLegacyThingiverseScraper)

    result = await service.scrape_thingiverse(access_token="token", test_mode=True, test_limit=2)

    assert result["status"] == "success"
    assert result["products_found"] == 3
    assert result["harness"] == "legacy"

    # Avoid leaking env toggles into other tests.
    os.environ.pop("THINGIVERSE_USE_CORE_HARNESS", None)


async def test_core_harness_run_that_finds_nothing_is_an_error(monkeypatch):
    service = ScraperService(_SupabaseStub())

    class EmptyAdapter:
        def __init__(self, supabase_client, access_token=None):
            pass

        async def enumerate_candidates(self, context):
            return []

        async def close(self):
            return None

    class FakeLegacyThingiverseScraper:
        def __init__(self, supabase_client, access_token=None):
            self.SEARCH_TERMS = []

        async def close(self):
            return None

    monkeypatch.setattr("services.scrapers.ThingiverseSourceAdapter", EmptyAdapter)
    monkeypatch.setattr("services.scrapers.ThingiverseScraper", FakeLegacyThingiverseScraper)

    result = await service.scrape_thingiverse(access_token="token", test_mode=False)

    assert result["status"] == "error"
    assert "found 0 products" in result["error_message"]
    assert result["harness"] == "core"
