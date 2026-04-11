"""
Thingiverse scraper for accessibility and assistive devices
Uses Thingiverse API with OAuth authentication
"""
import httpx
import math
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from .base_scraper import BaseScraper
from urllib.parse import quote


class ThingiverseScraper(BaseScraper):
    """
    Thingiverse scraper for accessibility and assistive devices
    
    Searches for 3D-printable accessibility aids and assistive devices
    """
    
    SEARCH_TERMS = [
        # Default terms encoded with '+' for spaces as expected
        'accessibility',
        'assistive+device',
        'arthritis+grip',
        'adaptive+tool',
        'mobility+aid',
        'tremor+stabilizer',
        'adaptive+utensil'
    ]
    
    API_BASE_URL = 'https://api.thingiverse.com'
    REQUESTS_PER_MINUTE = 5
    RESULTS_PER_PAGE = 20
    MAX_PAGES = 100  # Guard against unbounded pagination in case of broad terms
    USER_AGENT = "a11yhood-backend/thingiverse-scraper"
    
    def __init__(self, supabase_client, access_token: Optional[str] = None):
        super().__init__(supabase_client, access_token)
    
    def get_source_name(self) -> str:
        return 'thingiverse'
    
    def supports_url(self, url: str) -> bool:
        """Check if this URL is a Thingiverse URL"""
        return 'thingiverse.com' in url.lower()
    
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single Thingiverse thing URL"""
        try:
            if not self.access_token:
                return None
            
            # Extract thing ID from URL
            # Format: https://www.thingiverse.com/thing:123456
            import re
            match = re.search(r'thing:(\d+)', url)
            if not match:
                return None
            
            thing_id = match.group(1)
            
            # Fetch thing data from Thingiverse API
            thing_data = await self._fetch_thing_details(thing_id)
            if not thing_data:
                return None
            
            return self._create_product_dict(thing_data)
        except Exception as e:
            print(f"Error scraping Thingiverse URL: {e}")
            return None
    
    async def _fetch_thing_details(self, thing_id: str) -> Optional[Dict[str, Any]]:
        """Fetch thing details from Thingiverse API with debug output."""
        try:
            url = f"https://api.thingiverse.com/things/{thing_id}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "User-Agent": self.USER_AGENT,
            }
            await self._throttle_request()
            response = await self.client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                print(
                    f"[Thingiverse] Thing details status={response.status_code} id={thing_id} "
                    f"body={response.text[:200]}"
                )
            response.raise_for_status()
            data = response.json()
            print(
                f"[Thingiverse] Got details id={thing_id} name={data.get('name')} "
                f"public_url={data.get('public_url')}"
            )
            return data
        except Exception as e:
            print(f"[Thingiverse] Error fetching Thingiverse thing id={thing_id}: {e}")
        return None
    
    async def scrape(self, test_mode: bool = False, test_limit: int = 5) -> Dict[str, Any]:
        """
        Scrape Thingiverse for accessibility products
        
        Args:
            test_mode: If True, only scrape limited items for testing
            test_limit: Number of items to scrape in test mode
            
        Returns:
            Dict with scraping results (products_found, products_added, etc.)
        """
        # Initialize test-mode session for global item capping
        self._begin_test_session(test_mode, test_limit)

        if not self.access_token:
            raise ValueError("Thingiverse access token is required")
        
        start_time = datetime.now()
        products_found = 0
        products_added = 0
        products_updated = 0
        print(
            "[Thingiverse] Starting scrape",
            f"test_mode={test_mode}",
            f"test_limit={test_limit}",
            f"token_len={len(self.access_token) if self.access_token else 0}"
        )
        
        try:
            for term in self.SEARCH_TERMS:
                if test_mode and products_found >= test_limit:
                    break

                things = await self._search_things(term)
                if test_mode:
                    remaining = max(test_limit - products_found, 0)
                    if remaining <= 0:
                        break
                    if len(things) > remaining:
                        things = things[:remaining]
                print(f"[Thingiverse] term='{term}' hits={len(things)} (capped={test_mode})")
                # Debug: list hits returned for this term
                for t in things:
                    print(
                        f"[Thingiverse] term='{term}' hit id={t.get('id')} name={t.get('name')} url={t.get('public_url')}"
                    )
                
                for thing in things:
                    # Respect test limit after filtering
                    if test_mode and products_found >= test_limit:
                        break

                    print(f"[Thingiverse] Fetching details id={thing.get('id')} url={thing.get('public_url')}")

                    # Fetch full thing details
                    thing_details = await self._fetch_thing_details(thing['id'])

                    if not thing_details:
                        print(f"[Thingiverse] Skip id={thing.get('id')} (no details)")
                        continue
                    
                    # Add search term to thing details for tracking
                    thing_details['_search_term'] = term
                    
                    # Check if product already exists by URL
                    url = thing_details.get('public_url') or f"https://www.thingiverse.com/thing:{thing['id']}"
                    existing = await self._product_exists(url)
                    print(f"[Thingiverse] Exists? {bool(existing)} url={url}")

                    # Count this processed item for test-mode limiting
                    products_found += 1

                    if existing:
                        # Update existing product
                        result = await self._update_product(existing["id"], thing_details)
                        if result:
                            products_updated += 1
                            print(f"[Thingiverse] Updated existing product url={url} (found via term='{term}')")
                        else:
                            print(f"[Thingiverse] Failed to update existing product url={url}")
                    else:
                        # Add new product
                        result = await self._create_product(thing_details)
                        if result:
                            products_added += 1
                            print(f"[Thingiverse] Added product url={url} (found via term='{term}')")
                        else:
                            print(f"[Thingiverse] Failed to add product url={url}")
            
            duration = (datetime.now() - start_time).total_seconds()
            print(
                "[Thingiverse] Finished scrape",
                f"found={products_found}",
                f"added={products_added}",
                f"updated={products_updated}",
                f"duration_sec={duration:.2f}"
            )
            
            return {
                'source': 'Thingiverse',
                'products_found': products_found,
                'products_added': products_added,
                'products_updated': products_updated,
                'duration_seconds': duration,
                'status': 'success',
            }
            
        except Exception as e:
            print(f"[Thingiverse] Fatal scrape error: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            return {
                'source': 'Thingiverse',
                'products_found': products_found,
                'products_added': products_added,
                'products_updated': products_updated,
                'duration_seconds': duration,
                'status': 'error',
                'error_message': str(e),
            }
    
    async def _search_things(self, term: str) -> List[Dict[str, Any]]:
        """Search Thingiverse for things matching a term with pagination via helper.

        Uses the documented `GET /search` endpoint with `q` query parameter.
        """
        hits: List[Dict[str, Any]] = []
        per_page = self.RESULTS_PER_PAGE

        async for page_hits in self._paginate(
            lambda page: self._fetch_things_page(term, page, per_page),
            max_pages=self.MAX_PAGES,
            respect_test_limit=True,
        ):
            hits.extend(page_hits)

        return hits

    async def _fetch_things_page(self, term: str, page: int, per_page: int) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch a single Thingiverse search page and indicate if more pages remain."""
        url = f"{self.API_BASE_URL}/search/{term}/"

        try:
            response = await self.client.get(
                url,
                params={
                    "type": "things",
                    "page": page,
                    "per_page": per_page,
                },
                headers={
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json',
                    'User-Agent': self.USER_AGENT,
                },
                timeout=15.0,
            )
            if response.status_code in (401, 403):
                print(
                    f"[Thingiverse] Auth error status={response.status_code} term='{term}' body={response.text[:200]}"
                )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                print(
                    f"[Thingiverse] API response type=list page={page} n={len(data)} keys_first={list(data[0].keys())[:5] if data else []}"
                )
                page_hits = data
            else:
                keys = list(data.keys())
                page_hits = data.get('hits', [])
                print(
                    f"[Thingiverse] API response type=dict page={page} keys={keys[:8]} hits_len={len(page_hits)}"
                )

            if not page_hits:
                print(
                    f"[Thingiverse] Empty search results term='{term}' page={page} status={response.status_code} "
                    f"body={response.text[:300]}"
                )
                return [], False

            has_more = len(page_hits) >= per_page
            return page_hits, has_more

        except httpx.HTTPError as e:
            print(f"[Thingiverse] Error searching for term '{term}' page={page}: {e}")
            return [], False

    @staticmethod
    def _matches_search_term(thing: Dict[str, Any], term: str) -> bool:
        """
        Ensure the returned Thingiverse item actually matches the search term.

        Matching strategy:
        - Split the search term into words (by whitespace)
        - Build a combined lowercased text from name, description, tags, categories
        - Require that ALL words from the term appear in the combined text
        """
        try:
            if not term:
                return True

            # Normalize term into words (spaces or hyphens treated as separators)
            raw = term.lower().replace('+', ' ')
            words = [w for w in raw.replace('-', ' ').split() if w]
            if not words:
                return True

            # Collect candidate text fields
            name = (thing.get('name') or '').lower()
            description = (thing.get('description') or '').lower()
            tags = []
            for tag in thing.get('tags') or []:
                t = tag.get('name') or tag.get('tag')
                if t:
                    tags.append(t.lower())
            categories = [cat.get('name', '').lower() for cat in (thing.get('categories') or [])]

            combined = ' '.join([name, description, ' '.join(tags), ' '.join(categories)])

            return all(word in combined for word in words)
        except Exception:
            # If anything goes wrong, do not exclude
            return True
    
    def _is_image_url(self, url: Optional[str]) -> bool:
        if not url:
            return False
        url_lower = url.lower()
        return url_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'))

    def _create_product_dict(self, thing: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Thingiverse thing data to product dict"""
        # Extract image URL; avoid picking non-image assets (e.g., .stl)
        image = None
        if thing.get('default_image') and self._is_image_url(thing['default_image'].get('url')):
            image = thing['default_image'].get('url')
        elif thing.get('thumbnail') and self._is_image_url(thing['thumbnail']):
            image = thing['thumbnail']
        else:
            # Fallback: try images array and pick the largest valid image
            images = thing.get('images') or []
            for img in images:
                sizes = img.get('sizes') or []
                # Prefer the largest size first by reversing
                for size in reversed(sizes):
                    candidate = size.get('url')
                    if self._is_image_url(candidate):
                        image = candidate
                        break
                if image:
                    break
        
        # Extract tags
        tags = []
        if thing.get('tags'):
            raw_tags = [tag.get('name') or tag.get('tag') for tag in thing['tags'] if tag.get('name') or tag.get('tag')]
            # Deduplicate while preserving order
            seen = set()
            for tag in raw_tags:
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
        
        url = thing.get('public_url') or f"https://www.thingiverse.com/thing:{thing['id']}"
        
        # Use "makes" as the popularity signal (Thingiverse hearts aren't capped and don't map to stars)
        makes_raw = (
            thing.get('make_count')
            or thing.get('makes')
            or thing.get('makes_count')
            or thing.get('made_count')
            or 0
        )
        try:
            makes = int(makes_raw) if makes_raw is not None else 0
        except (TypeError, ValueError):
            makes = 0

        # Convert makes to a continuous 1–5 rating using a log10 scale.
        # Formula: clamp(1 + log10(makes), 1.0, 5.0)
        # Anchor points: 1→1.0, 10→2.0, 100→3.0, 1000→4.0, 10000→5.0.
        if makes > 0:
            rating = round(min(max(1.0 + math.log10(makes), 1.0), 5.0), 2)
        else:
            rating = None
        rating_count = makes if makes > 0 else None
        
        # Determine type based on thing properties (default to 3D Printed)
        product_type = 'Fabrication'
        categories = [cat.get('name', '').lower() for cat in thing.get('categories', [])]
        if any('laser' in cat or 'cut' in cat for cat in categories):
            product_type = 'Fabrication'
        
        # Extract last updated timestamp from Thingiverse
        # Thingiverse provides 'modified' or 'updated' field
        source_last_updated = None
        modified = thing.get('modified') or thing.get('updated')
        if modified:
            try:
                # Thingiverse returns ISO 8601 format
                source_last_updated = datetime.fromisoformat(modified.replace('Z', '+00:00'))
            except Exception as e:
                print(f"[Thingiverse] Failed to parse last updated date: {e}")
        
        # Extract search term if provided
        search_term = thing.get('_search_term')
        
        # Track which search term matched
        matched_search_terms = []
        if search_term:
            matched_search_terms.append(search_term)
        
        return {
            'name': thing['name'],
            'description': thing.get('description', ''),
            'url': url,
            'image': image,
            'source': 'Thingiverse',
            'type': product_type,
            'tags': tags,
            'scraped_at': datetime.now(),
            'external_id': str(thing['id']),
            'source_rating': rating,
            'source_rating_count': rating_count,
            'source_last_updated': source_last_updated,
            'matched_search_terms': matched_search_terms,
            'external_data': {
                'rating': rating,
                'rating_count': rating_count,
                'stars': rating_count or 0,
                'make_count': makes,
                'likes': thing.get('like_count', 0),
                'favorites': thing.get('favorite_count', 0),
                'categories': [cat.get('name') for cat in thing.get('categories', [])],
            }
        }
    
    async def _create_product(self, thing: Dict[str, Any]) -> bool:
        """Create a new product from Thingiverse thing"""
        return await super()._create_product(thing)
    
    async def _update_product(self, product_id: str, thing: Dict[str, Any]) -> bool:
        """Update existing product with latest Thingiverse data"""
        return await super()._update_product(product_id, thing)
