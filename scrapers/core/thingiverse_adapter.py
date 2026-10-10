import math
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .base_source_scraper import BaseSourceScraper
from .contracts import RateLimitPolicy, ScrapeRunContext


class ThingiverseSourceAdapter(BaseSourceScraper):
    """Lean Thingiverse adapter for the new source-scraper contract."""

    SEARCH_TERMS = [
        "accessibility",
        "assistive+device",
        "arthritis+grip",
        "adaptive+tool",
        "mobility+aid",
        "tremor+stabilizer",
        "adaptive+utensil",
    ]

    API_BASE_URL = "https://api.thingiverse.com"
    RESULTS_PER_PAGE = 20
    MAX_PAGES = 100
    USER_AGENT = "backend/thingiverse-scraper"

    def __init__(
        self,
        supabase_client,
        *,
        access_token: str | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        super().__init__(supabase_client, rate_limit_policy=rate_limit_policy)
        self.access_token = access_token

        if client is not None:
            self.client = client
        else:
            headers = {
                "Accept": "application/json",
                "User-Agent": self.USER_AGENT,
            }
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            self.client = httpx.AsyncClient(headers=headers)

    async def close(self) -> None:
        await self.client.aclose()

    def get_source_name(self) -> str:
        return "thingiverse"

    def supports_url(self, url: str) -> bool:
        return "thingiverse.com" in (url or "").lower()

    async def enumerate_candidates(self, context: ScrapeRunContext) -> list[dict]:
        collected: list[dict] = []

        for term in self.SEARCH_TERMS:
            page = 1
            while page <= self.MAX_PAGES:
                hits, has_more = await self._fetch_things_page(
                    term=term,
                    page=page,
                    per_page=self.RESULTS_PER_PAGE,
                )
                if not hits:
                    break

                for thing in hits:
                    if "_matched_search_term" not in thing:
                        thing["_matched_search_term"] = term

                    collected.append(thing)
                    if self.should_stop_collection(len(collected), context):
                        return collected

                if not has_more:
                    break

                page += 1

        return collected

    async def fetch_one(self, candidate: dict, context: ScrapeRunContext) -> dict | None:
        thing_id = candidate.get("id")
        if thing_id is None:
            source_url = candidate.get("source_url") or candidate.get("url") or ""
            thing_id = self._extract_thing_id(str(source_url))

        if thing_id is None:
            return None

        details = await self._fetch_thing_details(str(thing_id))
        if details is None:
            return None

        if candidate.get("_matched_search_term") and not details.get("_matched_search_term"):
            details["_matched_search_term"] = candidate["_matched_search_term"]

        return details

    def map_to_source_raw(self, raw: dict, context: ScrapeRunContext) -> dict:
        thing_id = raw.get("id")
        source_url = raw.get("public_url") or (
            f"https://www.thingiverse.com/thing:{thing_id}" if thing_id is not None else None
        )
        source_url = source_url or "https://www.thingiverse.com"

        makes = self._extract_make_count(raw)
        source_rating = self.map_makes_to_source_rating(makes)
        source_rating_count = makes if makes > 0 else None

        matched_search_terms: list[str] = []
        matched = raw.get("_matched_search_term")
        if matched:
            matched_search_terms.append(str(matched))

        image_url = self._extract_image_url(raw)
        name = str(raw.get("name") or "thingiverse-thing")

        image_alt = None
        if image_url:
            image_alt = f"{name} image (ALT text missing on source)"

        return {
            "source": self.get_source_name(),
            "external_id": str(thing_id or source_url),
            "source_url": source_url,
            "name": name,
            "description": raw.get("description") or "",
            "source_last_updated": self._parse_source_timestamp(raw),
            "matched_search_terms": matched_search_terms,
            "tags": self.generate_tags(raw, {}),
            "image_url": image_url,
            "image_alt": image_alt,
            "source_rating": source_rating,
            "source_rating_count": source_rating_count,
            "external_data": {
                "make_count": makes,
                "likes": raw.get("like_count") or 0,
                "favorites": raw.get("favorite_count") or 0,
                "categories": [
                    category.get("name")
                    for category in (raw.get("categories") or [])
                    if isinstance(category, dict) and category.get("name")
                ],
            },
        }

    def generate_tags(self, raw: dict, source_raw: dict) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        def add_tag(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                tags.append(text)

        # Product types were retired in favor of tags; everything here is fabrication.
        add_tag("fabrication")

        for tag in raw.get("tags") or []:
            if isinstance(tag, dict):
                add_tag(tag.get("name") or tag.get("tag"))
            else:
                add_tag(tag)

        for category in raw.get("categories") or []:
            if isinstance(category, dict):
                add_tag(category.get("name"))

        return tags

    @staticmethod
    def map_makes_to_source_rating(makes: int | None) -> float | None:
        if not makes or makes <= 0:
            return None
        return round(min(max(1.0 + math.log10(makes), 1.0), 5.0), 2)

    async def _fetch_things_page(
        self, term: str, page: int, per_page: int
    ) -> tuple[list[dict[str, Any]], bool]:
        response = await self.client.get(
            f"{self.API_BASE_URL}/search/{term}/",
            params={
                "type": "things",
                "page": page,
                "per_page": per_page,
            },
            timeout=20.0,
        )

        if response.status_code != 200:
            return [], False

        payload = response.json() if response.content else []
        if isinstance(payload, list):
            hits = payload
        else:
            hits = payload.get("hits") or []

        has_more = len(hits) >= per_page
        return hits, has_more

    async def _fetch_thing_details(self, thing_id: str) -> dict[str, Any] | None:
        response = await self.client.get(
            f"{self.API_BASE_URL}/things/{thing_id}",
            timeout=20.0,
        )
        if response.status_code != 200:
            return None

        return response.json() if response.content else None

    @staticmethod
    def _extract_thing_id(url: str) -> str | None:
        match = re.search(r"thing:(\d+)", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _is_image_url(url: str | None) -> bool:
        if not url:
            return False

        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".avif")

        parsed = urlparse(str(url).strip())
        path = unquote((parsed.path or "").lower())
        if path.endswith(image_exts):
            return True

        query = parse_qs(parsed.query)
        nested_urls = query.get("url", [])
        for nested in nested_urls:
            nested_path = unquote(urlparse(nested).path.lower())
            if nested_path.endswith(image_exts):
                return True

        return False

    def _extract_image_url(self, raw: dict[str, Any]) -> str | None:
        default_image = raw.get("default_image")
        if isinstance(default_image, dict):
            default_url = default_image.get("url")
            if self._is_image_url(default_url):
                return str(default_url)

        thumbnail = raw.get("thumbnail")
        if self._is_image_url(thumbnail):
            return str(thumbnail)

        for image in raw.get("images") or []:
            if not isinstance(image, dict):
                continue
            sizes = image.get("sizes") or []
            if not isinstance(sizes, list):
                continue
            for size in reversed(sizes):
                if not isinstance(size, dict):
                    continue
                candidate = size.get("url")
                if self._is_image_url(candidate):
                    return str(candidate)

        return None

    @staticmethod
    def _extract_make_count(raw: dict[str, Any]) -> int:
        makes_raw = (
            raw.get("make_count")
            or raw.get("makes")
            or raw.get("makes_count")
            or raw.get("made_count")
            or 0
        )
        try:
            return int(makes_raw) if makes_raw is not None else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_source_timestamp(raw: dict[str, Any]) -> str | None:
        value = str(raw.get("modified") or raw.get("updated") or "").strip()
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.isoformat()
        except ValueError:
            return None
