"""
Backend scraper service - handles OAuth and coordinates scraping
"""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from scrapers.core.contracts import ScrapeMode, ScrapeRunContext
from scrapers.core.github_adapter import GitHubSourceAdapter
from scrapers.core.ravelry_adapter import RavelrySourceAdapter
from scrapers.core.thingiverse_adapter import ThingiverseSourceAdapter
from scrapers.github import GitHubScraper
from scrapers.ravelry import RavelryScraper
from scrapers.thingiverse import ThingiverseScraper

logger = logging.getLogger(__name__)


class ScraperOAuth:
    """Handle OAuth flows for different platforms"""

    @staticmethod
    async def get_ravelry_token(
        client_id: str, client_secret: str, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        """Exchange Ravelry OAuth code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.ravelry.com/oauth2/token",
                auth=(client_id, client_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def get_thingiverse_token(
        client_id: str, client_secret: str, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        """Exchange Thingiverse OAuth code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.thingiverse.com/login/oauth/access_token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def refresh_ravelry_token(
        client_id: str, client_secret: str, refresh_token: str
    ) -> dict[str, Any]:
        """Refresh Ravelry access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.ravelry.com/oauth2/token",
                auth=(client_id, client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()


class ScraperService:
    """Coordinate scraping operations"""

    # How long a scraper_locks row is honored before being treated as
    # abandoned (e.g. a serverless invocation that crashed mid-scrape without
    # releasing its lock).
    _SCRAPE_LOCK_STALE_AFTER = timedelta(minutes=30)

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    @staticmethod
    def _truthy_env(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    # Sentinel lock_token used when the lock table itself is unreachable: the
    # run proceeds (fails open) without ever writing a lock row, so release
    # must recognize this value and skip the delete rather than matching
    # some other run's real row.
    _NO_LOCK_TOKEN = ""

    def _try_acquire_scrape_lock(self, source: str) -> str | None:
        """Best-effort lock stopping two scrape runs for the same source from
        overlapping (e.g. an admin's manual trigger firing while the daily
        cron for that source is still running, or a retried cron invocation).

        Overlapping runs both pass the check-then-insert in
        scrapers/base_scraper.py's _product_exists()/_create_product() before
        either commits, which trips idx_products_source_external_id.

        Returns the lock_token to pass to _release_scrape_lock when it's safe
        to proceed (either a real token identifying the acquired row, or
        _NO_LOCK_TOKEN when failing open because the lock table itself is
        unreachable), or None when another run currently holds the lock.

        The returned token matters for correctness, not just bookkeeping: a
        run whose lock is reclaimed as stale (see below) must not have its
        eventual release delete the *new* owner's row. Release only deletes
        when the row's current lock_token still matches what this call
        acquired, so a stale reclaim safely fences off the original owner.
        """
        try:
            stale_cutoff = (datetime.now(UTC) - self._SCRAPE_LOCK_STALE_AFTER).isoformat()
            # Clear a lock abandoned by a crashed/timed-out run before trying to acquire.
            self.supabase.table("scraper_locks").delete().eq("source", source).lt(
                "locked_at", stale_cutoff
            ).execute()

            result = (
                self.supabase.table("scraper_locks")
                .upsert({"source": source}, on_conflict="source", ignore_duplicates=True)
                .execute()
            )
            if not result.data:
                return None
            return result.data[0]["lock_token"]
        except Exception as e:
            logger.warning("Lock acquisition failed for '%s', proceeding without it: %s", source, e)
            return self._NO_LOCK_TOKEN

    def _release_scrape_lock(self, source: str, lock_token: str) -> None:
        if lock_token == self._NO_LOCK_TOKEN:
            return
        try:
            self.supabase.table("scraper_locks").delete().eq("source", source).eq(
                "lock_token", lock_token
            ).execute()
        except Exception as e:
            logger.warning("Failed to release scrape lock for '%s': %s", source, e)

    @staticmethod
    def _scrape_skipped_result(source: str) -> dict[str, Any]:
        # "halted" (not a new "skipped" value) because scraping_logs.status has
        # a CHECK constraint limited to success/error/halted.
        return {
            "source": source,
            "products_found": 0,
            "products_added": 0,
            "products_updated": 0,
            "duration_seconds": 0,
            "status": "halted",
            "error_message": f"Scrape already in progress for {source}",
        }

    def _load_platform_terms(self, platform: str) -> list[str] | None:
        """Load persisted search terms for a platform from either schema variant."""
        try:
            response = (
                self.supabase.table("scraper_search_terms")
                .select("search_terms")
                .eq("platform", platform)
                .limit(1)
                .execute()
            )
            terms = (response.data or [{}])[0].get("search_terms") if response.data else None
            if not (isinstance(terms, list) and terms):
                normalized = (
                    self.supabase.table("scraper_search_terms")
                    .select("search_term")
                    .eq("platform", platform)
                    .execute()
                )
                terms = [
                    row.get("search_term")
                    for row in (normalized.data or [])
                    if row.get("search_term")
                ]

            return terms if isinstance(terms, list) and terms else None
        except Exception:
            return None

    async def _load_platform_token(self, platform: str) -> str | None:
        try:
            config_response = (
                self.supabase.table("oauth_configs")
                .select("access_token")
                .eq("platform", platform)
                .execute()
            )
            token = (
                (config_response.data or [{}])[0].get("access_token")
                if config_response.data
                else None
            )
            return token
        except Exception:
            return None

    async def _scrape_thingiverse_legacy(
        self, access_token: str | None, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        """Legacy Thingiverse implementation kept as a safe fallback."""
        scraper = ThingiverseScraper(self.supabase, access_token)
        terms = self._load_platform_terms("thingiverse")
        if terms:
            scraper.SEARCH_TERMS = terms

        try:
            result = await scraper.scrape(test_mode=test_mode, test_limit=test_limit)
            result["harness"] = "legacy"
            return result
        finally:
            await scraper.close()

    async def _scrape_thingiverse_core(
        self, access_token: str | None, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        """Run Thingiverse via core adapter enumeration/fetch with legacy persistence layer."""
        if not access_token:
            raise ValueError("Thingiverse access token is required")

        adapter = ThingiverseSourceAdapter(self.supabase, access_token=access_token)
        persistence = ThingiverseScraper(self.supabase, access_token)

        terms = self._load_platform_terms("thingiverse")
        if terms:
            adapter.SEARCH_TERMS = terms
            persistence.SEARCH_TERMS = terms

        mode = ScrapeMode.FULL_SOURCE_TEST_N if test_mode else ScrapeMode.FULL_SOURCE
        context = ScrapeRunContext(mode=mode, max_products=test_limit if test_mode else None)

        start_time = datetime.now(UTC)
        products_found = 0
        products_added = 0
        products_updated = 0

        try:
            candidates = await adapter.enumerate_candidates(context)

            for candidate in candidates:
                raw = await adapter.fetch_one(candidate, context)
                if not raw:
                    continue

                products_found += 1

                thing_id = raw.get("id")
                url = raw.get("public_url") or (
                    f"https://www.thingiverse.com/thing:{thing_id}" if thing_id is not None else None
                )
                if not url:
                    continue

                existing = await persistence._product_exists(
                    url,
                    external_id=str(thing_id) if thing_id is not None else None,
                    source=persistence.get_source_name(),
                )

                if existing:
                    result = await persistence._update_product(existing["id"], raw)
                    if result:
                        products_updated += 1
                else:
                    result = await persistence._create_product(raw)
                    if result:
                        products_added += 1

            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "Thingiverse",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "success",
                "harness": "core",
            }
        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "Thingiverse",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "error",
                "error_message": str(e),
                "harness": "core",
            }
        finally:
            await adapter.close()
            await persistence.close()

    async def _scrape_github_legacy(
        self, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        token = await self._load_platform_token("github")
        if not token:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_ACCESS_TOKEN")

        scraper = GitHubScraper(self.supabase, access_token=token)
        terms = self._load_platform_terms("github")
        if terms:
            scraper.SEARCH_TERMS = terms
        try:
            result = await scraper.scrape(test_mode=test_mode, test_limit=test_limit)
            result["harness"] = "legacy"
            return result
        finally:
            await scraper.close()

    async def _scrape_github_core(
        self, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        token = await self._load_platform_token("github")
        if not token:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_ACCESS_TOKEN")

        adapter = GitHubSourceAdapter(self.supabase, access_token=token)
        persistence = GitHubScraper(self.supabase, access_token=token)

        terms = self._load_platform_terms("github")
        if terms:
            adapter.SEARCH_TERMS = terms
            persistence.SEARCH_TERMS = terms

        mode = ScrapeMode.FULL_SOURCE_TEST_N if test_mode else ScrapeMode.FULL_SOURCE
        context = ScrapeRunContext(mode=mode, max_products=test_limit if test_mode else None)

        start_time = datetime.now(UTC)
        products_found = 0
        products_added = 0
        products_updated = 0

        try:
            candidates = await adapter.enumerate_candidates(context)
            for candidate in candidates:
                raw = await adapter.fetch_one(candidate, context)
                if not raw:
                    continue

                products_found += 1

                url = raw.get("html_url") or raw.get("url")
                full_name = raw.get("full_name")
                if not url and full_name:
                    url = f"https://github.com/{full_name}"
                if not url:
                    continue

                external_id = raw.get("id") or raw.get("node_id")
                existing = await persistence._product_exists(
                    url,
                    external_id=str(external_id) if external_id is not None else None,
                    source=persistence.get_source_name(),
                )

                if existing:
                    result = await persistence._update_product(existing["id"], raw)
                    if result:
                        products_updated += 1
                else:
                    result = await persistence._create_product(raw)
                    if result:
                        products_added += 1

            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "GitHub",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "success",
                "harness": "core",
            }
        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "GitHub",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "error",
                "error_message": str(e),
                "harness": "core",
            }
        finally:
            await adapter.close()
            await persistence.close()

    async def _scrape_ravelry_legacy(
        self, access_token: str, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        scraper = RavelryScraper(self.supabase, access_token)
        cats = self._load_platform_terms("ravelry_pa_categories")
        if cats:
            scraper.PA_CATEGORIES = cats
        try:
            result = await scraper.scrape(test_mode=test_mode, test_limit=test_limit)
            result["harness"] = "legacy"
            return result
        finally:
            await scraper.close()

    async def _scrape_ravelry_core(
        self, access_token: str, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        adapter = RavelrySourceAdapter(self.supabase, access_token=access_token)
        persistence = RavelryScraper(self.supabase, access_token)

        cats = self._load_platform_terms("ravelry_pa_categories")
        if cats:
            adapter.PA_CATEGORIES = cats
            persistence.PA_CATEGORIES = cats

        mode = ScrapeMode.FULL_SOURCE_TEST_N if test_mode else ScrapeMode.FULL_SOURCE
        context = ScrapeRunContext(mode=mode, max_products=test_limit if test_mode else None)

        start_time = datetime.now(UTC)
        products_found = 0
        products_added = 0
        products_updated = 0

        try:
            candidates = await adapter.enumerate_candidates(context)
            for candidate in candidates:
                raw = await adapter.fetch_one(candidate, context)
                if not raw:
                    continue

                products_found += 1

                permalink = str(raw.get("permalink") or "").strip()
                url = raw.get("url") or (
                    f"https://www.ravelry.com/patterns/library/{permalink}"
                    if permalink
                    else None
                )
                if not url:
                    continue

                external_id = raw.get("id") or permalink
                existing = await persistence._product_exists(
                    url,
                    external_id=str(external_id) if external_id else None,
                    source=persistence.get_source_name(),
                )

                if existing:
                    result = await persistence._update_product(existing["id"], raw)
                    if result:
                        products_updated += 1
                else:
                    result = await persistence._create_product(raw)
                    if result:
                        products_added += 1

            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "Ravelry",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "success",
                "harness": "core",
            }
        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "Ravelry",
                "products_found": products_found,
                "products_added": products_added,
                "products_updated": products_updated,
                "duration_seconds": duration,
                "status": "error",
                "error_message": str(e),
                "harness": "core",
            }
        finally:
            await adapter.close()
            await persistence.close()

    async def scrape_thingiverse(
        self, access_token: str | None, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        """Scrape Thingiverse for accessibility products."""
        lock_token = self._try_acquire_scrape_lock("thingiverse")
        if lock_token is None:
            return self._scrape_skipped_result("Thingiverse")
        try:
            use_core_harness = self._truthy_env("THINGIVERSE_USE_CORE_HARNESS", True)
            if use_core_harness:
                return await self._scrape_thingiverse_core(
                    access_token=access_token,
                    test_mode=test_mode,
                    test_limit=test_limit,
                )

            return await self._scrape_thingiverse_legacy(
                access_token=access_token,
                test_mode=test_mode,
                test_limit=test_limit,
            )
        finally:
            self._release_scrape_lock("thingiverse", lock_token)

    async def scrape_ravelry(
        self, access_token: str, test_mode: bool = False, test_limit: int = 5
    ) -> dict[str, Any]:
        """Scrape Ravelry for accessibility patterns."""
        lock_token = self._try_acquire_scrape_lock("ravelry")
        if lock_token is None:
            return self._scrape_skipped_result("Ravelry")
        try:
            use_core_harness = self._truthy_env("RAVELRY_USE_CORE_HARNESS", True)
            if use_core_harness:
                return await self._scrape_ravelry_core(
                    access_token=access_token,
                    test_mode=test_mode,
                    test_limit=test_limit,
                )

            return await self._scrape_ravelry_legacy(
                access_token=access_token,
                test_mode=test_mode,
                test_limit=test_limit,
            )
        finally:
            self._release_scrape_lock("ravelry", lock_token)

    async def scrape_github(self, test_mode: bool = False, test_limit: int = 5) -> dict[str, Any]:
        """Scrape GitHub for assistive technology repositories."""
        lock_token = self._try_acquire_scrape_lock("github")
        if lock_token is None:
            return self._scrape_skipped_result("GitHub")
        try:
            use_core_harness = self._truthy_env("GITHUB_USE_CORE_HARNESS", True)
            if use_core_harness:
                return await self._scrape_github_core(test_mode=test_mode, test_limit=test_limit)
            return await self._scrape_github_legacy(test_mode=test_mode, test_limit=test_limit)
        finally:
            self._release_scrape_lock("github", lock_token)
            await scraper.close()
