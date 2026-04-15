"""
LibraryThing scraper for books with accessibility information
Uses LibraryThing Web Services API to fetch book metadata and accessibility details
"""

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from .base_scraper import BaseScraper


class GOATScraper(BaseScraper):
    """
    GOATScraper scraper for accessibility items stored by GOAT in librarything.com

    Fetches book metadata and common knowledge data from GOAT
    including title, author, description, cover image, and accessibility notes
    """

    API_BASE_URL = "https://www.librarything.com/services/rest/1.1"
    REQUESTS_PER_MINUTE = 60  # LibraryThing allows 1000/day = ~0.7/min, being conservative

    def __init__(self, supabase_client, access_token: str | None = None):
        super().__init__(supabase_client, access_token)
        # API key can be passed as access_token or read from config
        self.api_key = access_token
        # Override client with proper headers for LibraryThing API
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "a11yhood/1.0 (https://a11yhood.org; contact@a11yhood.org)",
                "Accept": "application/xml, text/xml",
            },
            timeout=30.0,
        )

    def get_source_name(self) -> str:
        return "goat"

    def supports_url(self, url: str) -> bool:
        """Check if this URL is a LibraryThing URL"""
        return "librarything.com" in url.lower()

    async def scrape_url(self, url: str) -> dict[str, Any] | None:
        """Scrape a single LibraryThing book URL"""
        try:
            # Extract work ID from URL
            # Format: https://www.librarything.com/work/35356138/book/302275636
            # or: https://www.librarything.com/work/35356138
            work_id = self._extract_work_id(url)
            if not work_id:
                return None

            # Fetch work data from LibraryThing API
            work_data = await self._fetch_work_details(work_id)
            if not work_data:
                return None

            return self._create_product_dict(work_data, url)
        except Exception as e:
            print(f"Error scraping LibraryThing URL: {e}")
            return None

    def _extract_work_id(self, url: str) -> str | None:
        """Extract work ID from LibraryThing URL"""
        match = re.search(r"/work/(\d+)", url)
        return match.group(1) if match else None

    async def _fetch_work_details(self, work_id: str) -> dict[str, Any] | None:
        """Fetch work details from LibraryThing API"""
        try:
            if not self.api_key:
                print("[LibraryThing] API key not configured")
                return None

            # LibraryThing API endpoint - note: some endpoints may require different formats
            url = f"{self.API_BASE_URL}/"
            params = {
                "method": "librarything.ck.getwork",
                "id": work_id,
                "apikey": self.api_key,
            }

            print(f"[LibraryThing] Requesting: {url} with params: {params}")

            await self._throttle_request()

            try:
                response = await self.client.get(
                    url, params=params, timeout=30.0, follow_redirects=True
                )
            except httpx.HTTPStatusError as e:
                print(f"[LibraryThing] HTTP error: {e}")
                return None
            except httpx.TimeoutException:
                print(f"[LibraryThing] Request timeout for work {work_id}")
                return None

            if response.status_code != 200:
                print(
                    f"[LibraryThing] Work details status={response.status_code} id={work_id} "
                    f"body={response.text[:500]}"
                )
                return None

            # Parse XML response
            work_data = self._parse_xml_response(response.text, work_id)
            if work_data:
                print(
                    f"[LibraryThing] Got details id={work_id} title={work_data.get('title')} "
                    f"author={work_data.get('author')}"
                )
            return work_data
        except Exception as e:
            print(f"[LibraryThing] Error fetching work id={work_id}: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _parse_xml_response(self, xml_text: str, work_id: str) -> dict[str, Any] | None:
        """Parse XML response from LibraryThing API"""
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_text)

            # Check for errors
            error = root.find("error")
            if error is not None:
                error_msg = error.findtext("message", "Unknown error")
                print(f"[LibraryThing] API error: {error_msg}")
                return None

            # Extract work data
            work = root.find("work")
            if work is None:
                print("[LibraryThing] No work element found in response")
                return None

            # Extract basic fields
            title = work.findtext("title", "").strip()
            if not title:
                print(f"[LibraryThing] No title found for work {work_id}")
                return None

            # Get author information
            author_elem = work.find("author")
            author = None
            if author_elem is not None:
                author = (
                    author_elem.findtext("name", "").strip()
                    or author_elem.findtext("authorname", "").strip()
                )

            # Get description/summary
            description = None
            descriptions = work.findall("description")
            for desc_elem in descriptions:
                desc_text = desc_elem.text
                if desc_text and desc_text.strip():
                    description = desc_text.strip()
                    break

            # Get cover image
            image_url = None
            covers = work.findall("cover")
            for cover_elem in covers:
                cover_id = cover_elem.findtext("id", "").strip()
                if cover_id:
                    # LibraryThing cover image format
                    image_url = f"https://covers.librarything.com/pics/{cover_id}l"
                    break

            # Get tags and accessibility notes
            tags = []
            popular_tags = work.find("populartags")
            if popular_tags is not None:
                for tag_elem in popular_tags.findall("tag"):
                    tag_name = tag_elem.findtext("name", "").strip()
                    if tag_name:
                        tags.append(tag_name)

            # Get book language and other metadata
            language = work.findtext("language", "").strip()
            publication_year = work.findtext("publicationyear", "").strip()

            return {
                "work_id": work_id,
                "title": title,
                "author": author,
                "description": description,
                "image_url": image_url,
                "tags": tags,
                "language": language,
                "publication_year": publication_year,
                "url": f"https://www.librarything.com/work/{work_id}",
            }
        except ET.ParseError as e:
            print(f"[LibraryThing] XML parse error: {e}")
            return None
        except Exception as e:
            print(f"[LibraryThing] Error parsing response: {e}")
            return None

    async def scrape(
        self,
        test_mode: bool = False,
        test_limit: int = 5,
        urls: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Bulk scraping for GOAT (LibraryThing) via REST API.

        ⚠️  IMPORTANT: LibraryThing REST API is protected by CloudFlare and may block requests.
        As of December 2024, bulk API access is unreliable due to bot protection.

        Alternative approaches:
        1. Use scrape_url() for individual books from the web interface
        2. Use LibraryThing export features if you have a collection
        3. Contact LibraryThing for API access arrangements

        This method loads LibraryThing targets (URLs or work IDs) from the
        provided urls argument or from scraper_search_terms (platform=goat),
        and fetches them via the REST API. Access may still fail due to
        CloudFlare protection.

        Args:
            test_mode: If True, only scrape limited items for testing
            test_limit: Number of items to scrape in test mode

        Returns:
            Dict with scraping results
        """
        start_time = datetime.now(UTC)
        results = {
            "source": "GOAT",
            "products_found": 0,
            "products_added": 0,
            "products_updated": 0,
            "duration_seconds": 0,
            "status": "success",
        }

        try:
            if not self.api_key:
                results["status"] = "warning"
                results["message"] = (
                    "LibraryThing API key not configured. Cannot scrape without API key. Configure in oauth_configs table with platform=goat"
                )
                return results

            # Determine targets: explicit URLs take precedence; otherwise load search_terms
            targets: list[str] = []
            if urls:
                targets = urls
            else:
                try:
                    response = (
                        self.supabase.table("scraper_search_terms")
                        .select("search_term")
                        .eq("platform", "goat")
                        .execute()
                    )
                    if response.data:
                        targets = [
                            item["search_term"] for item in response.data if item.get("search_term")
                        ]
                except Exception as e:
                    print(f"[LibraryThing] Error loading targets from database: {e}")

            if not targets:
                results["status"] = "warning"
                results["message"] = (
                    "No GOAT targets configured. Provide LibraryThing URLs or work IDs via urls argument or scraper_search_terms (platform=goat)."
                )
                duration = (datetime.now(UTC) - start_time).total_seconds()
                results["duration_seconds"] = duration
                return results

            print(f"[LibraryThing] Starting GOAT scrape of {len(targets)} targets")
            print("[LibraryThing] ⚠️  Note: API requests may be blocked by CloudFlare protection")

            # Scrape each target: treat URLs first, otherwise assume work_id
            for i, target in enumerate(targets):
                if test_mode and i >= test_limit:
                    print(f"[LibraryThing] Test mode: stopping after {test_limit} targets")
                    break

                try:
                    work_id = None
                    source_url = None

                    if isinstance(target, str) and target.startswith("http"):
                        source_url = target
                        work_id = self._extract_work_id(target)
                    else:
                        work_id = str(target).strip() if target is not None else None

                    if not work_id:
                        print(f"[LibraryThing] Skipping target without work id: {target}")
                        continue

                    # Fetch work details
                    work_data = await self._fetch_work_details(work_id)
                    if not work_data:
                        print(
                            f"[LibraryThing] Could not fetch work {work_id} (likely blocked by CloudFlare)"
                        )
                        continue

                    print(
                        f"[LibraryThing] Fetched work data: {work_data.get('title')} (ID: {work_id})"
                    )

                    # Build product payload
                    product_payload = self._create_product_dict(work_data, source_url)

                    # Check if product already exists
                    product_url = (
                        product_payload.get("url") or f"https://www.librarything.com/work/{work_id}"
                    )
                    existing = await self._product_exists(product_url)

                    if existing:
                        print(f"[LibraryThing] Updating existing product: {existing.get('id')}")
                        success = await self._update_product(existing["id"], product_payload)
                        if success:
                            results["products_updated"] += 1
                            print(f"[LibraryThing] ✓ Updated: {product_payload.get('name')}")
                        else:
                            print(
                                f"[LibraryThing] ✗ Failed to update: {product_payload.get('name')}"
                            )
                    else:
                        print(f"[LibraryThing] Creating new product: {product_payload.get('name')}")
                        success = await self._create_product(product_payload)
                        if success:
                            results["products_added"] += 1
                            print(f"[LibraryThing] ✓ Created: {product_payload.get('name')}")
                        else:
                            print(
                                f"[LibraryThing] ✗ Failed to create: {product_payload.get('name')}"
                            )

                    results["products_found"] += 1

                except Exception as e:
                    print(f"[LibraryThing] Error processing target {target}: {e}")
                    import traceback

                    traceback.print_exc()
                    continue

            duration = (datetime.now(UTC) - start_time).total_seconds()
            results["duration_seconds"] = duration

            if results["products_found"] == 0:
                results["status"] = "warning"
                results["message"] = (
                    "No works could be fetched. LibraryThing API is likely blocked by CloudFlare. Use scrape_url() for individual books instead."
                )
            else:
                results["message"] = (
                    f"Scraped {results['products_found']} works (API may have limited access)"
                )

            return results

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()
            return {
                "source": "GOAT",
                "products_found": 0,
                "products_added": 0,
                "products_updated": 0,
                "duration_seconds": duration,
                "status": "error",
                "error_message": f"Scraper error: {str(e)}. Note: LibraryThing API may be blocked by CloudFlare.",
            }

    def _create_product_dict(
        self, work_data: dict[str, Any], source_url: str | None = None
    ) -> dict[str, Any]:
        """Convert LibraryThing work data to product format"""
        title = work_data.get("title", "Untitled")
        author = work_data.get("author")

        # Build description with author if available
        description = work_data.get("description")
        if author and description:
            description = f"By {author}\n\n{description}"
        elif author:
            description = f"By {author}"

        # Add metadata to description
        if work_data.get("publication_year"):
            if description:
                description += f"\n\nPublished: {work_data['publication_year']}"
            else:
                description = f"Published: {work_data['publication_year']}"

        if work_data.get("language"):
            lang = work_data["language"]
            if description:
                description += f"\nLanguage: {lang}"
            else:
                description = f"Language: {lang}"

        # Extract last updated timestamp
        source_last_updated = None
        if work_data.get("last_updated"):
            try:
                source_last_updated = work_data["last_updated"]
                if isinstance(source_last_updated, datetime):
                    source_last_updated = source_last_updated.isoformat()
            except Exception as e:
                print(f"[LibraryThing] Failed to parse last updated date: {e}")

        # Build product dict using standard field names (consistent with other scrapers)
        product_data = {
            "name": title,
            "description": description,
            "source": "GOAT",
            "url": source_url or work_data.get("url"),  # Use 'url' not 'source_url'
            "image": work_data.get("image_url"),  # Use 'image' not 'image_url'
            "type": "Book",
            "external_id": work_data.get("work_id"),
            "tags": work_data.get("tags", []),
            "scraped_at": datetime.now(UTC).isoformat(),
            "source_last_updated": source_last_updated,
        }

        return product_data

    async def _create_product(self, raw_data: dict[str, Any]) -> bool:
        """Create a new product from LibraryThing work data"""
        return await super()._create_product(raw_data)

    async def _update_product(self, product_id: str, raw_data: dict[str, Any]) -> bool:
        """Update existing product with latest LibraryThing data"""
        return await super()._update_product(product_id, raw_data)
