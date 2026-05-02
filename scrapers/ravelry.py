"""
Ravelry scraper for accessibility knitting/crochet patterns
Uses Ravelry API with OAuth2 authentication
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .base_scraper import BaseScraper


class RavelryScraper(BaseScraper):
    """
    Ravelry scraper for accessibility patterns

    Searches Ravelry's pattern-accessibility (PA) categories for
    knitting and crochet patterns designed for accessibility needs
    """

    # Pattern-attribute slugs for accessibility-related patterns. Include known variants to avoid missing results
    # if the API expects the full slug (e.g., "mobility-aid-accessory").
    PA_CATEGORIES = [
        "medical-device-access",
        "medical-device-accessory",
        "mobility-aid-accessory",
        "other-accessibility",
        "adaptive",
        "therapy-aid",
    ]

    API_BASE_URL = "https://api.ravelry.com"
    REQUESTS_PER_MINUTE = 5
    RESULTS_PER_PAGE = 50

    def __init__(self, supabase_client, access_token: str | None = None):
        super().__init__(supabase_client, access_token)
        # Ravelry API expects OAuth2 bearer tokens; keep Accept by default for JSON responses
        default_headers = {"Accept": "application/json"}
        if access_token:
            default_headers["Authorization"] = f"Bearer {access_token}"
        self.client = httpx.AsyncClient(headers=default_headers)

    def get_source_name(self) -> str:
        return "ravelry"

    def supports_url(self, url: str) -> bool:
        """Check if this URL is a Ravelry URL"""
        return "ravelry.com" in url.lower()

    async def scrape_url(self, url: str) -> dict[str, Any] | None:
        """Scrape a single Ravelry pattern/project URL"""
        try:
            if not self.access_token:
                return None

            # Extract pattern ID from URL
            # Format: https://www.ravelry.com/patterns/library/pattern-name or /projects/username/project-name
            import re

            # Try to extract pattern ID
            pattern_match = re.search(r"/patterns/library/([a-z0-9-]+)", url)
            if pattern_match:
                pattern_id = pattern_match.group(1)
                pattern_data = await self._fetch_pattern_details(pattern_id)
                if pattern_data:
                    return self._create_product_dict(pattern_data)

            return None
        except Exception as e:
            print(f"Error scraping Ravelry URL: {e}")
            return None

    async def scrape(self, test_mode: bool = False, test_limit: int = 5) -> dict[str, Any]:
        """
        Scrape Ravelry for accessibility patterns

        Args:
            test_mode: If True, only scrape limited items for testing
            test_limit: Number of items to scrape in test mode

        return {
            Dict with scraping results (products_found, products_added, etc.)
        """
        # Initialize test-mode and auth failure tracking
        self._begin_test_session(test_mode, test_limit)
        self._reset_auth_failure_state()

        if not self.access_token:
            raise ValueError("Ravelry access token is required")
        start_time = datetime.now(UTC)
        products_found = 0
        products_added = 0
        products_updated = 0
        print(
            f"[Ravelry] Starting scrape test_mode={test_mode} test_limit={test_limit} token_len={len(self.access_token) if self.access_token else 0}"
        )

        try:
            for pa_category in self.PA_CATEGORIES:
                if test_mode and products_found >= test_limit:
                    break

                category_count = 0
                pages_seen = 0

                print(f"[Ravelry] Category='{pa_category}' starting pagination")
                async for patterns in self._paginate(
                    lambda page: self._search_patterns(pa_category, page), respect_test_limit=True
                ):
                    pages_seen += 1
                    if test_mode and products_found >= test_limit:
                        break

                    if test_mode:
                        remaining = max(test_limit - products_found, 0)
                        if remaining <= 0:
                            break
                        if len(patterns) > remaining:
                            patterns = patterns[:remaining]

                    for pattern in patterns:
                        if test_mode and products_found >= test_limit:
                            break

                        category_count += 1
                        products_found += 1

                        pattern_id = pattern.get("id")
                        full_pattern = await self._fetch_pattern_details(pattern_id)

                        if not full_pattern:
                            print(
                                f"[Ravelry] Failed to fetch details for pattern {pattern_id}, skipping"
                            )
                            continue

                        # Track which PA category matched this pattern
                        full_pattern["_matched_pa_category"] = pa_category

                        url = (
                            f"https://www.ravelry.com/patterns/library/{full_pattern['permalink']}"
                        )
                        existing = await self._product_exists(
                            url,
                            external_id=str(full_pattern["id"]),
                            source=self.get_source_name(),
                        )

                        if existing:
                            result = await self._update_product(existing["id"], full_pattern)
                            if result:
                                products_updated += 1
                        else:
                            result = await self._create_product(full_pattern)
                            if result:
                                products_added += 1

                if category_count and pages_seen:
                    print(
                        f"[Ravelry] Category '{pa_category}' has {category_count} patterns across {pages_seen} pages"
                    )

                if test_mode and products_found >= test_limit:
                    break

            # Use base class helper to build result with auth failure handling
            return self._build_scrape_result(
                start_time=start_time,
                products_found=products_found,
                products_added=products_added,
                products_updated=products_updated,
            )

        except Exception as e:
            # Use base class helper to build error result
            return self._build_scrape_result(
                start_time=start_time,
                products_found=products_found,
                products_added=products_added,
                products_updated=products_updated,
                error=e,
            )

    async def _search_patterns(
        self, pa_category: str, page: int
    ) -> tuple[list[dict[str, Any]], bool]:
        """Search Ravelry patterns by PA slug.

        Returns a tuple of (patterns, has_more).
        """
        url = f"{self.API_BASE_URL}/patterns/search.json"
        # 'pa' is the Ravelry search parameter for pattern attributes
        params = {
            "pa": pa_category,
            "page_size": self.RESULTS_PER_PAGE,
            "page": page,
            "sort": "best",
        }
        try:
            print(f"[Ravelry] GET {url} params={params}")
            data = await self._get_with_refresh(url, params)
            if isinstance(data, dict):
                print(f"[Ravelry] Response keys page={page}: {list(data.keys())[:8]}")
            patterns = data.get("patterns", [])
            if not patterns and page == 1:
                print(f"[Ravelry] No results for category '{pa_category}' (page 1)")
            has_more = len(patterns) >= self.RESULTS_PER_PAGE
            return patterns, has_more
        except httpx.HTTPError as e:
            print(f"[Ravelry] Error searching PA category '{pa_category}' page {page}: {e}")
            return [], False

    async def _fetch_pattern_details(self, pattern_id: int | str) -> dict[str, Any] | None:
        """Fetch full pattern details by ID or permalink"""
        url = f"{self.API_BASE_URL}/patterns/{pattern_id}.json"
        try:
            data = await self._get_with_refresh(url)
            pattern = data.get("pattern") or (data.get("patterns") or [None])[0]
            return pattern
        except httpx.HTTPError as e:
            print(f"[Ravelry] Error fetching pattern {pattern_id}: {e}")
            return None

    async def _refresh_oauth_token(self) -> bool:
        """Refresh Ravelry OAuth token using stored refresh_token; returns True if refreshed"""
        if self._refresh_in_progress:
            # Avoid concurrent refresh storms
            return False
        self._refresh_in_progress = True
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
                print(
                    "[Ravelry] Cannot refresh token: missing client_id/client_secret/refresh_token"
                )
                return False
            async with httpx.AsyncClient() as http_client:
                token_resp = await http_client.post(
                    "https://www.ravelry.com/oauth2/token",
                    auth=(client_id, client_secret),
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        # Ravelry expects redirect_uri in refresh requests per error message
                        "redirect_uri": cfg.get("redirect_uri"),
                    },
                )
                if token_resp.status_code != 200:
                    print(
                        f"[Ravelry] Token refresh failed: {token_resp.status_code} {token_resp.text}"
                    )
                    return False
                token_data = token_resp.json()
                new_access = token_data.get("access_token")
                new_refresh = token_data.get("refresh_token", refresh_token)
                if not new_access:
                    print("[Ravelry] Token refresh failed: no access_token in response")
                    return False
                # Update db
                update_payload = {
                    "access_token": new_access,
                    "refresh_token": new_refresh,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                if token_data.get("expires_in"):
                    expires_at = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])
                    update_payload["token_expires_at"] = expires_at.isoformat()
                self.supabase.table("oauth_configs").update(update_payload).eq(
                    "platform", "ravelry"
                ).execute()
                # Update client header for subsequent requests
                self.client.headers["Authorization"] = f"Bearer {new_access}"
                return True
        except Exception as exc:
            print(f"[Ravelry] Token refresh exception: {exc}")
            return False
        finally:
            self._refresh_in_progress = False

    def _create_product_dict(self, pattern: dict[str, Any]) -> dict[str, Any]:
        """Convert Ravelry pattern data to product format"""
        # Extract image URL - try multiple sources
        image = None

        # Try first_photo first
        if pattern.get("first_photo"):
            if isinstance(pattern["first_photo"], dict):
                image = (
                    pattern["first_photo"].get("medium_url")
                    or pattern["first_photo"].get("small_url")
                    or pattern["first_photo"].get("thumbnail_url")
                )
            elif isinstance(pattern["first_photo"], str):
                image = pattern["first_photo"]

        # If no first_photo, try photos array
        if not image and pattern.get("photos"):
            photos = pattern["photos"]
            if isinstance(photos, list) and len(photos) > 0:
                first_photo = photos[0]
                if isinstance(first_photo, dict):
                    image = (
                        first_photo.get("medium_url")
                        or first_photo.get("small_url")
                        or first_photo.get("thumbnail_url")
                    )
                elif isinstance(first_photo, str):
                    image = first_photo

        # Determine type from craft type
        product_type = "Knitting"  # Default to knitting
        if pattern.get("craft"):
            craft_name = (
                pattern["craft"].get("name", "").lower()
                if isinstance(pattern["craft"], dict)
                else str(pattern["craft"]).lower()
            )
            if "crochet" in craft_name:
                product_type = "Crochet"
            elif "knit" in craft_name:
                product_type = "Knitting"

        # Extract pattern type tags
        tags = []
        if pattern.get("pattern_type"):
            type_name = (
                pattern["pattern_type"].get("name")
                if isinstance(pattern["pattern_type"], dict)
                else pattern["pattern_type"]
            )
            if type_name:
                tags.append(type_name)

        if pattern.get("pattern_categories"):
            for cat in pattern["pattern_categories"]:
                cat_name = cat.get("name") if isinstance(cat, dict) else cat
                if cat_name:
                    tags.append(cat_name)
                if isinstance(cat, dict) and cat.get("parent"):
                    parent_name = (
                        cat["parent"].get("name")
                        if isinstance(cat["parent"], dict)
                        else cat["parent"]
                    )
                    if parent_name:
                        tags.append(parent_name)

        # Add pattern_attributes (accessibility and other pattern attributes)
        if pattern.get("pattern_attributes"):
            for pa in pattern["pattern_attributes"]:
                if isinstance(pa, dict):
                    pa_name = pa.get("name") or pa.get("permalink", "").replace("-", " ").title()
                    if pa_name:
                        tags.append(pa_name)
                elif isinstance(pa, str):
                    tags.append(pa)

        # Add designer name as a tag if available
        if pattern.get("designer"):
            designer_name = (
                pattern["designer"].get("name")
                if isinstance(pattern["designer"], dict)
                else pattern["designer"]
            )
            if designer_name:
                tags.append(f"Designer: {designer_name}")

        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        pattern_url = f"https://www.ravelry.com/patterns/library/{pattern['permalink']}"

        # Description: Use notes_html or fall back to designer info
        description = pattern.get("notes_html", "").strip()
        if not description and pattern.get("designer"):
            designer_name = (
                pattern["designer"].get("name")
                if isinstance(pattern["designer"], dict)
                else pattern["designer"]
            )
            if designer_name:
                description = f"Pattern by {designer_name}"

        # Extract rating data from full pattern details
        rating = pattern.get("rating_average") or pattern.get("rating")
        rating_count = pattern.get("rating_count", 0)

        # Extract last updated timestamp from Ravelry
        # Ravelry provides 'updated_at' field for when the pattern was last modified
        source_last_updated = None
        updated_at = pattern.get("updated_at")
        if updated_at:
            try:
                # Ravelry returns custom format: '2019/08/29 20:22:16 -0400'
                # Parse it and convert to ISO format string for database storage
                from dateutil import parser

                parsed_date = parser.parse(updated_at)
                source_last_updated = parsed_date.isoformat()
            except Exception as e:
                print(f"[Ravelry] Failed to parse last updated date: {e}")

        # Track which PA category matched (passed via _matched_pa_category)
        matched_search_terms = []
        if pattern.get("_matched_pa_category"):
            matched_search_terms.append(pattern["_matched_pa_category"])

        return {
            "name": pattern["name"],
            "description": description,
            "source_url": pattern_url,
            "image": image,
            "source": "Ravelry",
            "type": product_type,
            "tags": unique_tags,
            "scraped_at": datetime.now().isoformat(),
            "external_id": str(pattern["id"]),
            "source_rating": rating,
            "source_rating_count": rating_count,
            "source_last_updated": source_last_updated,
            "matched_search_terms": matched_search_terms,
            "external_data": {
                "rating": rating,
                "rating_count": rating_count,
                "craft": pattern.get("craft", {}).get("name")
                if isinstance(pattern.get("craft"), dict)
                else pattern.get("craft"),
                "pattern_type": pattern.get("pattern_type", {}).get("name")
                if isinstance(pattern.get("pattern_type"), dict)
                else pattern.get("pattern_type"),
                "free": pattern.get("free"),
                "designer": pattern.get("designer", {}).get("name")
                if isinstance(pattern.get("designer"), dict)
                else pattern.get("designer"),
                "pattern_attributes": pattern.get("pattern_attributes", []),
                "pattern_categories": pattern.get("pattern_categories", []),
            },
        }

    async def _create_product(self, pattern: dict[str, Any]) -> bool:
        """Create a new product from Ravelry pattern"""
        return await super()._create_product(pattern)

    async def _update_product(self, product_id: str, pattern: dict[str, Any]) -> bool:
        """Update existing product with latest Ravelry data"""
        return await super()._update_product(product_id, pattern)
