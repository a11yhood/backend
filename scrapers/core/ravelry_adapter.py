from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .base_source_scraper import BaseSourceScraper
from .contracts import RateLimitPolicy, ScrapeRunContext


class RavelryAuthError(RuntimeError):
    """Ravelry rejected our credentials and a token refresh did not fix it."""


class RavelrySourceAdapter(BaseSourceScraper):
    """Lean Ravelry adapter for the new source-scraper contract."""

    API_BASE_URL = "https://api.ravelry.com"
    RESULTS_PER_PAGE = 50
    PA_CATEGORIES = [
        "medical-device-access",
        "medical-device-accessory",
        "mobility-aid-accessory",
        "other-accessibility",
        "adaptive",
        "therapy-aid",
    ]

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
            headers = {"Accept": "application/json"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            self.client = httpx.AsyncClient(headers=headers)

    async def close(self) -> None:
        await self.client.aclose()

    async def _refresh_access_token(self) -> bool:
        """Exchange the stored refresh_token for a new access token.

        Ravelry access tokens are short lived, so without this every scheduled
        run after the first expiry gets 401s. Returns True if the client now
        carries a fresh token.
        """
        try:
            resp = (
                self.supabase.table("oauth_configs")
                .select("client_id, client_secret, refresh_token, redirect_uri")
                .eq("platform", "ravelry")
                .limit(1)
                .execute()
            )
            cfg = (resp.data or [{}])[0]
            client_id = cfg.get("client_id")
            client_secret = cfg.get("client_secret")
            refresh_token = cfg.get("refresh_token")
            if not (client_id and client_secret and refresh_token):
                return False

            async with httpx.AsyncClient() as http_client:
                token_resp = await http_client.post(
                    "https://www.ravelry.com/oauth2/token",
                    auth=(client_id, client_secret),
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        # Ravelry expects redirect_uri on refresh requests
                        "redirect_uri": cfg.get("redirect_uri"),
                    },
                    timeout=20.0,
                )
            if token_resp.status_code != 200:
                return False

            token_data = token_resp.json()
            new_access = token_data.get("access_token")
            if not new_access:
                return False

            update_payload: dict[str, Any] = {
                "access_token": new_access,
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if token_data.get("expires_in"):
                expires_at = datetime.now(UTC) + timedelta(seconds=int(token_data["expires_in"]))
                update_payload["token_expires_at"] = expires_at.isoformat()
            self.supabase.table("oauth_configs").update(update_payload).eq(
                "platform", "ravelry"
            ).execute()

            self.access_token = new_access
            self.client.headers["Authorization"] = f"Bearer {new_access}"
            return True
        except Exception:
            return False

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET with one token refresh on 401/403; raises RavelryAuthError if still denied.

        Failing loudly matters: swallowing auth errors made an expired token look
        like a successful run that simply found nothing.
        """
        response = await self.client.get(url, timeout=20.0, **kwargs)
        if response.status_code in (401, 403):
            if await self._refresh_access_token():
                response = await self.client.get(url, timeout=20.0, **kwargs)
            if response.status_code in (401, 403):
                raise RavelryAuthError(
                    f"Ravelry API returned {response.status_code}; the OAuth token is "
                    "expired or revoked and could not be refreshed. Re-authorize Ravelry "
                    "in admin settings."
                )
        return response

    def get_source_name(self) -> str:
        return "ravelry"

    def supports_url(self, url: str) -> bool:
        return "ravelry.com" in (url or "").lower()

    async def enumerate_candidates(self, context: ScrapeRunContext) -> list[dict]:
        collected: list[dict] = []

        for pa_category in self.PA_CATEGORIES:
            page = 1
            while True:
                patterns, has_more = await self._search_patterns(pa_category=pa_category, page=page)
                if not patterns:
                    break

                for pattern in patterns:
                    if "_matched_pa_category" not in pattern:
                        pattern["_matched_pa_category"] = pa_category

                    collected.append(pattern)
                    if self.should_stop_collection(len(collected), context):
                        return collected

                if not has_more:
                    break
                page += 1

        return collected

    async def fetch_one(self, candidate: dict, context: ScrapeRunContext) -> dict | None:
        pattern_id = candidate.get("id")
        if pattern_id is None:
            source_url = candidate.get("source_url") or candidate.get("url") or ""
            parts = str(source_url).rstrip("/").split("/")
            if len(parts) >= 2:
                pattern_id = parts[-1]

        if pattern_id is None:
            return None

        details = await self._fetch_pattern_details(pattern_id)
        if details is None:
            return None

        if candidate.get("_matched_pa_category") and not details.get("_matched_pa_category"):
            details["_matched_pa_category"] = candidate["_matched_pa_category"]

        return details

    def map_to_source_raw(self, raw: dict, context: ScrapeRunContext) -> dict:
        permalink = str(raw.get("permalink") or "").strip()
        source_url = str(raw.get("url") or "").strip()
        if not source_url:
            source_url = (
                f"https://www.ravelry.com/patterns/library/{permalink}"
                if permalink
                else "https://www.ravelry.com"
            )

        image_url = self._extract_image_url(raw)
        image_alt = None
        if image_url:
            image_alt = (
                f"{raw.get('name', 'Ravelry pattern')} image (ALT text missing on source)"
            )

        matched_search_terms: list[str] = []
        matched = raw.get("_matched_pa_category")
        if matched:
            matched_search_terms.append(str(matched))

        rating = raw.get("rating_average")
        if rating is None:
            rating = raw.get("rating")
        source_rating = float(rating) if rating is not None else None
        source_rating_count = int(raw.get("rating_count") or 0)

        return {
            "source": self.get_source_name(),
            "external_id": str(raw.get("id") or permalink or source_url),
            "source_url": source_url,
            "name": raw.get("name") or permalink or "ravelry-pattern",
            "description": self._build_description(raw),
            "type": self._map_pattern_type(raw),
            "source_last_updated": self._parse_source_timestamp(raw),
            "matched_search_terms": matched_search_terms,
            "tags": self.generate_tags(raw, {}),
            "image_url": image_url,
            "image_alt": image_alt,
            "source_rating": source_rating,
            "source_rating_count": source_rating_count,
            "external_data": {
                "craft": self._extract_name(raw.get("craft")),
                "pattern_type": self._extract_name(raw.get("pattern_type")),
                "designer": self._extract_name(raw.get("designer")),
                "free": raw.get("free"),
                "pattern_attributes": raw.get("pattern_attributes") or [],
                "pattern_categories": raw.get("pattern_categories") or [],
            },
        }

    def generate_tags(self, raw: dict, source_raw: dict) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        def add_tag(value: str | None) -> None:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                tags.append(text)

        add_tag(self._extract_name(raw.get("pattern_type")))

        for category in raw.get("pattern_categories") or []:
            if isinstance(category, dict):
                add_tag(category.get("name"))
                parent = category.get("parent")
                if isinstance(parent, dict):
                    add_tag(parent.get("name"))
                else:
                    add_tag(parent)
            else:
                add_tag(str(category))

        for attr in raw.get("pattern_attributes") or []:
            if isinstance(attr, dict):
                add_tag(attr.get("name"))
            else:
                add_tag(str(attr))

        designer_name = self._extract_name(raw.get("designer"))
        if designer_name:
            add_tag(f"Designer: {designer_name}")

        return tags

    async def _search_patterns(self, pa_category: str, page: int) -> tuple[list[dict[str, Any]], bool]:
        params = {
            "pa": pa_category,
            "page_size": self.RESULTS_PER_PAGE,
            "page": page,
            "sort": "best",
        }
        response = await self._get(f"{self.API_BASE_URL}/patterns/search.json", params=params)
        if response.status_code != 200:
            return [], False

        payload = response.json() if response.content else {}
        patterns = payload.get("patterns") or []
        has_more = len(patterns) >= self.RESULTS_PER_PAGE
        return patterns, has_more

    async def _fetch_pattern_details(self, pattern_id: int | str) -> dict[str, Any] | None:
        response = await self._get(f"{self.API_BASE_URL}/patterns/{pattern_id}.json")
        if response.status_code != 200:
            return None

        payload = response.json() if response.content else {}
        pattern = payload.get("pattern")
        if pattern:
            return pattern

        patterns = payload.get("patterns") or []
        if patterns:
            return patterns[0]
        return None

    @staticmethod
    def _extract_name(value: Any) -> str | None:
        if isinstance(value, dict):
            return str(value.get("name") or "").strip() or None

        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _extract_image_url(raw: dict[str, Any]) -> str | None:
        first_photo = raw.get("first_photo")
        if isinstance(first_photo, dict):
            for key in ("medium_url", "small_url", "thumbnail_url"):
                value = str(first_photo.get(key) or "").strip()
                if value:
                    return value
        elif isinstance(first_photo, str) and first_photo.strip():
            return first_photo.strip()

        photos = raw.get("photos") or []
        if isinstance(photos, list) and photos:
            first = photos[0]
            if isinstance(first, dict):
                for key in ("medium_url", "small_url", "thumbnail_url"):
                    value = str(first.get(key) or "").strip()
                    if value:
                        return value
            elif isinstance(first, str) and first.strip():
                return first.strip()

        return None

    @staticmethod
    def _build_description(raw: dict[str, Any]) -> str:
        notes = str(raw.get("notes_html") or "").strip()
        if notes:
            return notes

        designer = RavelrySourceAdapter._extract_name(raw.get("designer"))
        if designer:
            return f"Pattern by {designer}"
        return ""

    @staticmethod
    def _map_pattern_type(raw: dict[str, Any]) -> str:
        craft_name = (RavelrySourceAdapter._extract_name(raw.get("craft")) or "").lower()
        if "crochet" in craft_name:
            return "Crochet"
        if "knit" in craft_name:
            return "Knitting"
        return "Knitting"

    @staticmethod
    def _parse_source_timestamp(raw: dict[str, Any]) -> str | None:
        value = str(raw.get("updated_at") or "").strip()
        if not value:
            return None

        try:
            parsed = datetime.strptime(value, "%Y/%m/%d %H:%M:%S %z")
            return parsed.isoformat()
        except ValueError:
            pass

        # Accept already-ISO values if Ravelry payload format changes.
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.isoformat()
        except ValueError:
            return None
