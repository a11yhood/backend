"""
Base scraper class and utility functions for all platform scrapers

This module provides:
1. BaseScraper - Abstract base class that all platform scrapers inherit from
   - Provides common methods for rate limiting, database operations, etc.
   - Each scraper must implement: scrape(), get_source_name(), and _create_product_dict()

2. ScraperUtilities - Static utility methods for scraper management
   - get_last_scrape_time() - Replacement for frontend ScraperService.getLastScrapeTime()
   - set_last_scrape_time() - Replacement for frontend ScraperService.setLastScrapeTime()
   - merge_scraped_products() - Replacement for frontend ScraperService.mergeScrapedProducts()

These utilities provide the same functionality that existed on the frontend,
but now operate on the backend with direct database access.
"""

import os
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import (
    Any,
    TypeVar,
)
from urllib.parse import urlparse, urlsplit

import httpx

from services.id_generator import normalize_to_snake_case

T = TypeVar("T")


class BaseScraper(ABC):
    """
    Base class for all platform scrapers

    Provides common functionality:
    - Rate limiting
    - Database operations
    - Product creation/update logic
    - Error handling
    - Test mode support
    """

    API_BASE_URL: str = ""
    REQUESTS_PER_MINUTE: int = 30

    def __init__(self, supabase_client, access_token: str | None = None):
        self.supabase = supabase_client
        self.access_token = access_token
        self._http_client: httpx.AsyncClient | None = None  # created lazily on first use
        self.last_request_time = 0.0
        self._supported_source_cache: dict[str, str] | None = None
        # Test-mode session state
        self._test_mode_enabled: bool = False
        self._test_mode_limit: int = 0
        self._test_mode_yielded: int = 0
        # OAuth auth failure tracking (used by scrapers with OAuth)
        self._had_auth_failure: bool = False
        self._last_auth_error: str | None = None
        self._refresh_in_progress: bool = False

    @property
    def client(self) -> httpx.AsyncClient:
        """Return the HTTP client, creating a default one on first access."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    @client.setter
    def client(self, value: httpx.AsyncClient) -> None:
        self._http_client = value

    async def close(self):
        """Clean up resources.

        Safe to call multiple times. Accessing ``client`` after closing will
        lazily create a new instance (consistent with normal lazy init behavior).
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    @abstractmethod
    async def scrape(self, test_mode: bool = False, test_limit: int = 5) -> dict[str, Any]:
        """
        Main scraping method - must be implemented by subclasses

        Args:
            test_mode: If True, only scrape limited items for testing
            test_limit: Number of items to scrape in test mode

        Returns:
            Dict with scraping results:
            {
                'source': str,
                'products_found': int,
                'products_added': int,
                'products_updated': int,
                'duration_seconds': float,
                'status': str,  # 'success' or 'error'
                'error_message': Optional[str]
            }
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the source name (e.g., 'github', 'ravelry', 'thingiverse')"""
        pass

    @staticmethod
    def _normalize_url(url: str | None) -> str | None:
        """Normalize URLs for consistent deduplication across scrapers.

        - Lowercase scheme/host
        - Strip trailing slashes
        - Collapse repeated slashes in path
        - Preserve Wayback Machine URLs (timestamp + inner URL)
        """
        if not url:
            return url
        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "http").lower()
            netloc = parsed.netloc.lower()
            raw_path = parsed.path or ""

            # Preserve inner archived URL in Wayback Machine paths (which contain ://)
            if netloc == "web.archive.org" and raw_path.startswith("/web/"):
                m = re.match(r"^/web/([^/]+)/(.+)$", raw_path)
                if m:
                    ts, inner = m.group(1), m.group(2)
                    inner = inner.rstrip("/")
                    path = f"/web/{ts}/{inner}"
                else:
                    path = raw_path.rstrip("/") or "/"
            else:
                path = re.sub(r"/+", "/", raw_path).rstrip("/") or "/"

            query = parsed.query
            return f"{scheme}://{netloc}{path}{('?' + query) if query else ''}"
        except Exception:
            return url

    async def _throttle_request(self):
        """Rate limiting to respect API limits.

        Calculates minimum interval between requests based on REQUESTS_PER_MINUTE.
        Sleeps if necessary to avoid exceeding rate limits and getting blocked.
        """
        import asyncio
        import time

        if self.REQUESTS_PER_MINUTE <= 0:
            return

        min_interval = 60.0 / self.REQUESTS_PER_MINUTE
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    async def _refresh_oauth_token(self) -> bool:
        """Refresh OAuth token for this scraper's platform.

        This is a base implementation that returns False. Scrapers that use OAuth
        should override this method to implement platform-specific token refresh logic.

        The implementation should:
        1. Fetch refresh_token and credentials from oauth_configs table
        2. Call the platform's token refresh endpoint
        3. Update oauth_configs table with new tokens
        4. Update self.client.headers["Authorization"] with new access token
        5. Return True if successful, False otherwise

        Returns:
            True if token was successfully refreshed, False otherwise
        """
        return False

    async def _get_with_refresh(
        self, url: str, params: dict[str, Any] | None = None, max_attempts: int = 2
    ) -> dict[str, Any]:
        """GET request with automatic OAuth token refresh on 401/403.

        This method handles the common pattern of retrying a request after refreshing
        an expired OAuth token. It will:
        1. Make the initial GET request
        2. If 401/403 received, call _refresh_oauth_token() (which scrapers can override)
        3. Retry the request once if refresh succeeded
        4. Track auth failures in _had_auth_failure/_last_auth_error

        Args:
            url: URL to GET
            params: Optional query parameters
            max_attempts: Maximum attempts (default 2: initial + 1 retry after refresh)

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: If request fails after all attempts
        """
        for attempt in range(1, max_attempts + 1):
            await self._throttle_request()
            response = await self.client.get(url, params=params)

            source_name = self.get_source_name()
            print(f"[{source_name}] HTTP attempt={attempt} status={response.status_code} url={url}")

            try:
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                # Try token refresh on first auth failure
                if attempt < max_attempts and status in (401, 403):
                    print(f"[{source_name}] Auth status={status}; attempting token refresh...")
                    refreshed = await self._refresh_oauth_token()
                    if refreshed:
                        print(f"[{source_name}] Token refreshed; retrying...")
                        continue

                # Final failure on auth error
                if status in (401, 403):
                    self._had_auth_failure = True
                    self._last_auth_error = f"{source_name} auth failed with status {status}; token refresh did not recover"

                raise

        # This point should be unreachable because we either return a response
        # or raise an HTTPStatusError in the loop above.
        raise RuntimeError(
            f"{self.get_source_name()} _get_with_refresh exited without returning or raising"
        )

    async def _paginate(
        self,
        fetch_page: Callable[[int], Awaitable[tuple[list[T], bool]]],
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        stop_on_empty: bool = True,
        respect_test_limit: bool = False,
    ) -> AsyncIterator[list[T]]:
        """Iterate through paginated API results without duplicating loops in scrapers.

        The ``fetch_page`` callback must return a tuple ``(items, has_more)`` where
        ``items`` is the list of results for the requested page and ``has_more``
        indicates whether additional pages might exist.

        - Pagination stops when ``has_more`` is False or ``max_pages`` is reached.
        - If ``stop_on_empty`` is True, an empty ``items`` list will end pagination
          unless ``has_more`` is True (allowing APIs that return empty pages to
          continue when signaled).
        """
        page = start_page
        while True:
            if max_pages is not None and page > max_pages:
                break

            items, has_more = await fetch_page(page)

            if items:
                if respect_test_limit and self._test_mode_enabled:
                    remaining = max(self._test_mode_limit - self._test_mode_yielded, 0)
                    if remaining <= 0:
                        break
                    if len(items) > remaining:
                        # Truncate items to remaining and stop pagination
                        truncated = items[:remaining]
                        self._test_mode_yielded += len(truncated)
                        yield truncated
                        break
                    else:
                        self._test_mode_yielded += len(items)
                        yield items
                else:
                    yield items
            elif stop_on_empty and not has_more:
                break

            if not has_more:
                break

            page += 1

    def _begin_test_session(self, test_mode: bool, test_limit: int):
        """Initialize test-mode counters for a scrape session.

        Scrapers should call this once at the beginning of `scrape()`.
        When `respect_test_limit=True` is passed to `_paginate`, pagination
        will stop after `test_limit` total items have been yielded across pages.
        """
        self._test_mode_enabled = bool(test_mode)
        self._test_mode_limit = int(test_limit or 0)
        self._test_mode_yielded = 0

    def _reset_auth_failure_state(self):
        """Reset OAuth auth failure tracking at the start of a scrape session.

        Scrapers using OAuth should call this at the beginning of scrape().
        """
        self._had_auth_failure = False
        self._last_auth_error = None

    def _build_scrape_result(
        self,
        start_time: datetime,
        products_found: int,
        products_added: int,
        products_updated: int,
        error: Exception | None = None,
    ) -> dict[str, Any]:
        """Build a standardized scrape result dictionary.

        Automatically includes auth failure information if applicable.

        Args:
            start_time: UTC datetime when scrape started
            products_found: Number of products discovered
            products_added: Number of new products created
            products_updated: Number of existing products updated
            error: Optional exception if scrape failed

        Returns:
            Standardized scrape result dict
        """
        duration = (datetime.now(UTC) - start_time).total_seconds()

        result = {
            "source": self.get_source_name(),
            "products_found": products_found,
            "products_added": products_added,
            "products_updated": products_updated,
            "duration_seconds": duration,
        }

        # Check for auth failure first (higher priority than generic errors)
        if self._had_auth_failure:
            result["status"] = "error"
            result["error_message"] = (
                self._last_auth_error
                or f"{self.get_source_name()} authentication failed during scrape"
            )
        elif error:
            result["status"] = "error"
            result["error_message"] = str(error)
        else:
            result["status"] = "success"

        return result

    async def _product_exists(
        self, url: str, external_id: str | None = None, source: str | None = None
    ) -> dict[str, Any] | None:
        """
        Check if a product already exists in the database.

        Deduplication priority:
        1. source + external_id (when both are provided) — most stable identity
        2. source_url (normalized) — fallback when no external_id

        Args:
            url: The product URL to check
            external_id: Optional external identifier from the source platform
            source: Optional source name (required for external_id lookup)

        Returns:
            Existing product dict if found, None otherwise
        """
        # 1. Try external_id + source match first (most reliable)
        if external_id and source:
            try:
                result = (
                    self.supabase.table("products")
                    .select("*")
                    .eq("source", source)
                    .eq("external_id", external_id)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    print(
                        f"[BaseScraper] Found existing product via external_id={external_id} source={source}"
                    )
                    return result.data[0]
            except Exception as e:
                print(f"[BaseScraper] external_id lookup failed: {e}")

        # 2. Fall back to source_url lookup
        normalized = self._normalize_url(url)
        try:
            result = (
                self.supabase.table("products")
                .select("*")
                .eq("source_url", normalized)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            if "column products.source_url does not exist" in str(e):
                print(
                    "[BaseScraper] products.source_url column missing in DB; "
                    "run the 20260418_migrate_url_to_source_url migration."
                )
                return None
            raise

    def _create_product_dict(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """
        Convert scraped data to product dict format
        Should be overridden by subclasses for platform-specific mapping

        Args:
            raw_data: Raw data from the platform API

        Returns:
            Product dict ready for database insertion
        """
        raise NotImplementedError("Subclasses must implement _create_product_dict")

    def _load_supported_sources(self) -> dict[str, str]:
        """Return cached supported_sources mapping of domain -> canonical name.

        Strips whitespace from domains/names to avoid duplicate variants like
        "Thingiverse " leaking into the products table. If the table is missing or the
        query fails, falls back to an empty mapping so scrapers can continue operating
        without blocking on the lookup.
        """
        if self._supported_source_cache is not None:
            return self._supported_source_cache

        try:
            result = self.supabase.table("supported_sources").select("domain,name").execute()
            mapping: dict[str, str] = {}
            for row in result.data or []:
                domain_raw = row.get("domain")
                name_raw = row.get("name")
                if not domain_raw or not name_raw:
                    continue
                domain = str(domain_raw).strip().lower()
                name = str(name_raw).strip()
                if not domain or not name:
                    continue
                mapping[domain] = name
            self._supported_source_cache = mapping
            return mapping
        except Exception as e:
            print(f"[BaseScraper] Warning: failed to load supported_sources: {e}")
            self._supported_source_cache = {}
            return {}

    def _canonicalize_source(self, product_data: dict[str, Any]) -> dict[str, Any]:
        """Map product_data['source'] to the canonical name from supported_sources based on URL domain.

        - If the product URL host matches a supported_sources.domain, replace the source with that row's name.
        - If no match, keep the existing source to avoid breaking inserts.
        """
        url = product_data.get("source_url")
        if not url:
            return product_data

        try:
            host = urlsplit(url).hostname
        except Exception:
            host = None

        if not host:
            return product_data

        domain = host.lower()
        supported = self._load_supported_sources()
        if domain in supported:
            product_data = {**product_data, "source": supported[domain]}

        return product_data

    def _slug_exists(self, slug: str) -> bool:
        result = self.supabase.table("products").select("id").eq("slug", slug).limit(1).execute()
        return bool(result.data)

    def _generate_unique_slug(self, base_value: str) -> str:
        base_slug = normalize_to_snake_case(base_value) or "product"
        if not self._slug_exists(base_slug):
            return base_slug
        for i in range(2, 500):
            candidate = f"{base_slug}-{i}"
            if not self._slug_exists(candidate):
                return candidate
        # Fallback to UUID suffix if many collisions
        return f"{base_slug}-{uuid.uuid4().hex[:6]}"

    def _ensure_slug(
        self, product_data: dict[str, Any], ensure_unique: bool = False
    ) -> dict[str, Any]:
        """Populate slug; optionally ensure uniqueness against DB."""
        if product_data.get("slug"):
            slug = product_data["slug"]
            if ensure_unique and self._slug_exists(slug):
                slug = self._generate_unique_slug(slug)
            return {**product_data, "slug": slug}

        base = product_data.get("name") or product_data.get("source_url") or "product"
        slug = (
            self._generate_unique_slug(base)
            if ensure_unique
            else (normalize_to_snake_case(base) or "product")
        )
        return {**product_data, "slug": slug}

    async def _create_product(self, raw_data: dict[str, Any]) -> bool:
        """
        Create a new product in the database

        Args:
            raw_data: Raw data from the platform API

        Returns:
            True if product was created successfully, False otherwise
        """
        product_data: dict[str, Any] | None = None
        tag_names: list[str] | None = None
        product_name = raw_data.get("name", raw_data.get("title", "UNKNOWN"))
        try:
            product_data = self._ensure_slug(
                self._create_product_dict(raw_data), ensure_unique=True
            )
            product_data = self._canonicalize_source(product_data)
            # Extract tags for relationship table; avoid inserting into products table
            tag_names = product_data.pop("tags", None)
            # Recursively convert any datetime fields to ISO strings
            product_data = self._convert_datetimes(product_data)
            result = self.supabase.table("products").insert(product_data).execute()
            created = result.data[0] if result.data else None
            if tag_names and created and created.get("id"):
                try:
                    from routers.products import set_product_tags

                    set_product_tags(self.supabase, created["id"], tag_names)
                except Exception as tag_err:
                    print(
                        f"[{self.get_source_name()}] Failed to set tags for '{product_name}': {tag_err}"
                    )
            if result.data:
                print(f"[{self.get_source_name()}] ✓ Created: {product_name}")
            return bool(result.data)
        except Exception as e:
            # Fall back if target schema is missing optional image fields
            if product_data and "Could not find the 'image' column" in str(e):
                sanitized = {
                    k: v for k, v in product_data.items() if k not in {"image", "image_alt"}
                }
                sanitized = self._convert_datetimes(sanitized)
                try:
                    result = self.supabase.table("products").insert(sanitized).execute()
                    created = result.data[0] if result.data else None
                    if tag_names and created and created.get("id"):
                        try:
                            from routers.products import set_product_tags

                            set_product_tags(self.supabase, created["id"], tag_names)
                        except Exception as tag_err:
                            print(
                                f"[{self.get_source_name()}] Failed to set tags after retry for '{product_name}': {tag_err}"
                            )
                    print(
                        "[BaseScraper] Retried insert without image fields due to missing column; update DB schema to include image/image_alt."
                    )
                    return bool(result.data)
                except Exception as retry_error:
                    print(
                        f"[{self.get_source_name()}] ✗ Failed to create '{product_name}' (retry): {retry_error}"
                    )
                    return False

            error_str = str(e)
            # Check for specific constraint violations
            if "duplicate key value violates unique constraint" in error_str:
                if "products_slug_key" in error_str:
                    print(
                        f"[{self.get_source_name()}] ✗ Skipped '{product_name}': Duplicate slug (product already exists or slug collision)"
                    )
                else:
                    print(
                        f"[{self.get_source_name()}] ✗ Skipped '{product_name}': Unique constraint violation: {error_str}"
                    )
            else:
                print(
                    f"[{self.get_source_name()}] ✗ Failed to create '{product_name}': {error_str}"
                )
            return False

    async def _update_product(self, product_id: str, raw_data: dict[str, Any]) -> bool:
        """
        Update an existing product in the database.

        Protects immutable fields (source, url, external_id) from modification.
        Preserves existing slug to avoid unique constraint conflicts on updates.

        Args:
            product_id: ID of the product to update
            raw_data: Raw data from the platform API

        Returns:
            True if product was updated successfully, False otherwise
        """
        product_name = raw_data.get("name", raw_data.get("title", "UNKNOWN"))
        try:
            product_data = self._create_product_dict(raw_data)
            product_data = self._canonicalize_source(product_data)
            tag_names = product_data.pop("tags", None)
            # Do not overwrite slug on update; only backfill if completely missing
            if not product_data.get("slug"):
                product_data = self._ensure_slug(product_data)
            # Don't update immutable fields
            product_data.pop("source", None)
            product_data.pop("source_url", None)
            product_data.pop("external_id", None)
            product_data.pop("scraped_at", None)  # Keep original scrape time
            product_data.pop("slug", None)  # Never update slug on existing product
            # Use ISO string to avoid JSON serialization failures when sending to Supabase
            product_data["updated_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
            # Recursively convert any datetime fields to ISO strings
            product_data = self._convert_datetimes(product_data)

            result = (
                self.supabase.table("products").update(product_data).eq("id", product_id).execute()
            )
            if tag_names is not None:
                try:
                    from routers.products import set_product_tags

                    set_product_tags(self.supabase, product_id, tag_names)
                except Exception as tag_err:
                    print(
                        f"[{self.get_source_name()}] Failed to set tags on update for '{product_name}': {tag_err}"
                    )
            if result.data:
                print(f"[{self.get_source_name()}] ✓ Updated: {product_name}")
            return bool(result.data)
        except Exception as e:
            error_str = str(e)
            if "Could not find the 'image' column" in error_str:
                sanitized = {
                    k: v for k, v in product_data.items() if k not in {"image", "image_alt"}
                }
                try:
                    result = (
                        self.supabase.table("products")
                        .update(self._convert_datetimes(sanitized))
                        .eq("id", product_id)
                        .execute()
                    )
                    if tag_names is not None:
                        try:
                            from routers.products import set_product_tags

                            set_product_tags(self.supabase, product_id, tag_names)
                        except Exception as tag_err:
                            print(
                                f"[{self.get_source_name()}] Failed to set tags on update after retry for '{product_name}': {tag_err}"
                            )
                    print(
                        "[BaseScraper] Retried update without image fields due to missing column; update DB schema to include image/image_alt."
                    )
                    return bool(result.data)
                except Exception as retry_error:
                    print(
                        f"[{self.get_source_name()}] ✗ Failed to update '{product_name}' (retry): {retry_error}"
                    )
                    return False
            print(f"[{self.get_source_name()}] ✗ Failed to update '{product_name}': {error_str}")
            return False

    @staticmethod
    def _convert_datetimes(obj: Any) -> Any:
        """Recursively convert datetime objects to ISO strings in dicts/lists.

        Ensures all payloads sent to Supabase are JSON-serializable.
        """
        from datetime import datetime

        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: BaseScraper._convert_datetimes(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [BaseScraper._convert_datetimes(v) for v in obj]
        return obj


class ScraperUtilities:
    """Utility functions for scraper management.

    Provides backend equivalents of deprecated frontend ScraperService methods.
    Used to track scrape timing and merge scraped products with existing data.
    """

    @staticmethod
    def get_last_scrape_time(supabase_client, source: str | None = None) -> datetime | None:
        """
        Get the last scrape time for a source (or all sources)

        Args:
            supabase_client: Supabase client instance
            source: Optional source name to filter by

        Returns:
            Last scrape datetime if found, None otherwise
        """
        try:
            query = (
                supabase_client.table("scraping_logs")
                .select("created_at")
                .order("created_at", desc=True)
                .limit(1)
            )

            if source:
                query = query.eq("source", source)

            result = query.execute()

            if result.data:
                return datetime.fromisoformat(result.data[0]["created_at"])
            return None
        except Exception as e:
            print(f"[ScraperUtilities] Error getting last scrape time: {e}")
            return None

    @staticmethod
    def _get_default_user_id(supabase_client) -> str | None:
        """Resolve a user id to attribute system-triggered scrapes."""
        env_user = os.getenv("SYSTEM_USER_ID") or os.getenv("ADMIN_USER_ID")
        if env_user:
            return env_user
        try:
            admin = (
                supabase_client.table("users").select("id").eq("role", "admin").limit(1).execute()
            )
            if admin.data:
                return admin.data[0]["id"]
        except Exception as e:
            print(f"[ScraperUtilities] Error resolving fallback user id: {e}")
        return None

    @staticmethod
    def set_last_scrape_time(
        supabase_client, source: str, scrape_result: dict[str, Any], user_id: str | None = None
    ) -> bool:
        """
        Record a scraping session in the logs

        Args:
            supabase_client: Supabase client instance
            source: Source name (e.g., 'github', 'ravelry', 'thingiverse')
            scrape_result: Dict containing scraping results

        Returns:
            True if log was created successfully, False otherwise
        """
        try:
            resolved_user_id = (
                user_id
                or scrape_result.get("user_id")
                or ScraperUtilities._get_default_user_id(supabase_client)
            )
            if not resolved_user_id:
                print(
                    "[ScraperUtilities] Skipping scrape log because no user_id is available; set SYSTEM_USER_ID or ADMIN_USER_ID."
                )
                return False

            log_data = {
                "source": source,
                "products_found": scrape_result.get("products_found", 0),
                "products_added": scrape_result.get("products_added", 0),
                "products_updated": scrape_result.get("products_updated", 0),
                "duration_seconds": scrape_result.get("duration_seconds", 0),
                "status": scrape_result.get("status", "success"),
                "error_message": scrape_result.get("error_message"),
                "user_id": resolved_user_id,
            }

            result = supabase_client.table("scraping_logs").insert(log_data).execute()
            return bool(result.data)
        except Exception as e:
            print(f"[ScraperUtilities] Error setting scrape time: {e}")
            return False

    @staticmethod
    async def merge_scraped_products(
        supabase_client, scraped_products: list, existing_products: list
    ) -> dict[str, list]:
        """
        Determine which products need to be added or updated

        Args:
            supabase_client: Supabase client instance
            scraped_products: List of scraped product dicts
            existing_products: List of existing products from database

        Returns:
            Dict with 'to_add' and 'to_update' lists
        """
        existing_urls = {p["source_url"]: p for p in existing_products if "source_url" in p}

        to_add = []
        to_update = []

        for scraped in scraped_products:
            url = scraped.get("source_url")
            if not url:
                continue

            if url in existing_urls:
                # Product exists, check if it needs updating
                existing = existing_urls[url]
                # Simple heuristic: update if name or description changed
                if scraped.get("name") != existing.get("name") or scraped.get(
                    "description"
                ) != existing.get("description"):
                    scraped["id"] = existing["id"]
                    to_update.append(scraped)
            else:
                # New product
                to_add.append(scraped)

        return {"to_add": to_add, "to_update": to_update}
