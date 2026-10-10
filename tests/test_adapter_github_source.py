from scrapers.core import GitHubSourceAdapter, ScrapeMode, ScrapeRunContext


def test_github_source_adapter_supports_url():
    adapter = GitHubSourceAdapter(supabase_client=None)

    assert adapter.supports_url("https://github.com/octocat/hello-world")
    assert not adapter.supports_url("https://example.com/project")


def test_github_source_adapter_generate_tags_deduplicates_and_keeps_language():
    adapter = GitHubSourceAdapter(supabase_client=None)

    tags = adapter.generate_tags(
        {
            "topics": ["assistive-tech", "screen-reader", "assistive-tech", ""],
            "language": "Python",
        },
        {},
    )

    assert tags == ["assistive-tech", "screen-reader", "Python"]


def test_github_source_adapter_maps_repo_to_source_product():
    adapter = GitHubSourceAdapter(supabase_client=None)
    context = ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT, matched_search_terms=["assistive"])

    source_product = adapter.map_to_source_product(
        {
            "id": 123,
            "name": "awesome-a11y",
            "description": "Accessibility tools",
            "html_url": "https://github.com/example/awesome-a11y?utm_source=test",
            "stargazers_count": 1800,
            "owner": {"avatar_url": "https://images.example/avatar.png"},
            "language": "Python",
            "topics": ["assistive-tech", "screen-reader"],
            "pushed_at": "2026-04-16T12:00:00Z",
            "_matched_search_term": "assistive technology",
        },
        context,
    )

    assert source_product.source == "github"
    assert source_product.external_id == "123"
    assert source_product.source_url == "https://github.com/example/awesome-a11y"
    assert source_product.name == "awesome-a11y"
    assert source_product.tags == ["assistive-tech", "screen-reader", "Python"]
    assert source_product.source_rating_count == 1800
    assert source_product.source_rating is not None
    assert source_product.matched_search_terms == ["assistive technology"]


def test_github_source_adapter_prefers_image_with_alt_text():
    adapter = GitHubSourceAdapter(supabase_client=None)
    context = ScrapeRunContext(mode=ScrapeMode.SINGLE_PRODUCT)

    source_product = adapter.map_to_source_product(
        {
            "id": 456,
            "name": "image-rich-repo",
            "description": "Repo with README images",
            "html_url": "https://github.com/example/image-rich-repo",
            "owner": {"avatar_url": "https://images.example/avatar.png"},
            "_image_candidates": [
                {"url": "https://images.example/no-alt.png", "alt": ""},
                {"url": "https://images.example/has-alt.png", "alt": "Accessibility diagram"},
            ],
        },
        context,
    )

    assert source_product.image_url == "https://images.example/has-alt.png"
    assert source_product.image_alt == "Accessibility diagram"


def test_github_source_adapter_extract_readme_images_resolves_relative_paths():
    adapter = GitHubSourceAdapter(supabase_client=None)

    markdown = (
        "![Alt text](images/hero.png)\n"
        "![ ](/assets/banner.jpg)\n"
        '<img src="https://cdn.example/img.png" alt="CDN image">\n'
    )

    images = adapter._extract_readme_images(
        markdown,
        owner="octocat",
        repo="hello-world",
        default_branch="main",
        readme_path="docs/README.md",
    )

    assert images[0] == {
        "url": "https://raw.githubusercontent.com/octocat/hello-world/main/docs/images/hero.png",
        "alt": "Alt text",
    }
    assert images[1] == {
        "url": "https://raw.githubusercontent.com/octocat/hello-world/main/assets/banner.jpg",
        "alt": "",
    }
    assert images[2] == {
        "url": "https://cdn.example/img.png",
        "alt": "CDN image",
    }


def test_github_source_adapter_map_stars_to_source_rating_anchors():
    assert GitHubSourceAdapter.map_stars_to_source_rating(0) is None
    assert GitHubSourceAdapter.map_stars_to_source_rating(10) == 1.0
    assert GitHubSourceAdapter.map_stars_to_source_rating(100) == 2.0
    assert GitHubSourceAdapter.map_stars_to_source_rating(1000) == 3.0
    assert GitHubSourceAdapter.map_stars_to_source_rating(10000) == 4.0


async def test_github_source_adapter_enumerate_candidates_full_depth(monkeypatch):
    adapter = GitHubSourceAdapter(supabase_client=None)
    adapter.SEARCH_TERMS = ["term-a", "term-b"]

    async def fake_fetch(term: str, page: int):
        if term == "term-a" and page == 1:
            return [
                {"id": 1, "name": "real-tool", "description": "assistive tool"},
                {"id": 2, "name": "awesome-a11y-list", "description": "curated list"},
            ], True
        if term == "term-a" and page == 2:
            return [{"id": 3, "name": "another-tool", "description": "helpful software"}], False
        if term == "term-b" and page == 1:
            return [{"id": 4, "name": "voice-tool", "description": "speech access"}], False
        return [], False

    monkeypatch.setattr(adapter, "_fetch_repositories", fake_fetch)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE)
    results = await adapter.enumerate_candidates(context)

    ids = [item["id"] for item in results]
    assert ids == [1, 2, 3, 4]
    assert results[0]["_matched_search_term"] == "term-a"
    assert results[3]["_matched_search_term"] == "term-b"


async def test_github_source_adapter_enumerate_candidates_respects_max_products(monkeypatch):
    adapter = GitHubSourceAdapter(supabase_client=None)
    adapter.SEARCH_TERMS = ["term-a", "term-b"]

    async def fake_fetch(term: str, page: int):
        if term == "term-a" and page == 1:
            return [
                {"id": 1, "name": "repo-1", "description": "tool"},
                {"id": 2, "name": "repo-2", "description": "tool"},
                {"id": 3, "name": "repo-3", "description": "tool"},
            ], True
        if term == "term-a" and page == 2:
            return [{"id": 4, "name": "repo-4", "description": "tool"}], False
        if term == "term-b" and page == 1:
            return [{"id": 5, "name": "repo-5", "description": "tool"}], False
        return [], False

    monkeypatch.setattr(adapter, "_fetch_repositories", fake_fetch)

    context = ScrapeRunContext(mode=ScrapeMode.FULL_SOURCE_TEST_N, max_products=3)
    results = await adapter.enumerate_candidates(context)

    assert [item["id"] for item in results] == [1, 2, 3]
