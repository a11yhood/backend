"""
GitHub scraper for accessibility and assistive technology projects
Uses GitHub REST API to search for repositories focused on assistive technologies
"""
import httpx
import math
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from .base_scraper import BaseScraper


class GitHubScraper(BaseScraper):
    """
    GitHub scraper for accessibility and assistive technology projects.
    
    Search strategy: Uses multiple targeted search terms to find diverse assistive tech.
    Focuses on tools and software that address disability access needs:
    - Screen readers and text-to-speech
    - Eye tracking and alternative input methods
    - Speech recognition and voice control
    - Switch access for severe motor disabilities
    - Mobility aids and assistive devices
    
    Filters out generic accessibility guidelines/documentation projects
    to focus on actual tools and software implementations.
    """
    
    SEARCH_TERMS = [
        'assistive technology',
        'screen reader',
        'eye tracking',
        'speech recognition',
        'switch access',
        'alternative input',
        'text-to-speech',
        'voice control',
        'accessibility aid',
        'mobility aid software'
    ]
    
    API_BASE_URL = 'https://api.github.com'
    REQUESTS_PER_MINUTE = 30
    RESULTS_PER_PAGE = 20
    
    def __init__(self, supabase_client, access_token: Optional[str] = None):
        super().__init__(supabase_client, access_token)
        headers = {"Accept": "application/vnd.github.v3+json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        # Use a dedicated client so we can attach auth headers if present.
        self.client = httpx.AsyncClient(headers=headers)
    
    def get_source_name(self) -> str:
        return 'github'
    
    def supports_url(self, url: str) -> bool:
        """Check if this URL is a GitHub URL"""
        return 'github.com' in url.lower()
    
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single GitHub repository URL"""
        try:
            # Extract owner/repo from URL
            # Format: https://github.com/owner/repo (additional path segments are ignored)
            parts = url.rstrip('/').split('/')
            if len(parts) < 5 or parts[2] != 'github.com':
                return None
            
            owner = parts[3]
            repo = parts[4]
            
            # Fetch repo data from GitHub API
            repo_data = await self._fetch_repo_details(owner, repo)
            if not repo_data:
                return None
            
            return self._create_product_dict(repo_data)
        except Exception as e:
            print(f"Error scraping GitHub URL: {e}")
            return None
    
    async def _fetch_repo_details(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetch repository details from GitHub API"""
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            await self._throttle_request()
            response = await self.client.get(url, timeout=10.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching GitHub repo: {e}")
        return None
    
    async def scrape(self, test_mode: bool = False, test_limit: int = 5) -> Dict[str, Any]:
        """
        Scrape GitHub for accessibility repositories
        
        Args:
            test_mode: If True, only scrape limited items for testing
            test_limit: Number of items to scrape in test mode
            
        Returns:
            Dict with scraping results (products_found, products_added, etc.)
        """
        # Initialize test-mode session for global item capping
        self._begin_test_session(test_mode, test_limit)

        start_time = datetime.now()
        products_found = 0
        products_added = 0
        products_updated = 0
        
        try:
            for term_index, term in enumerate(self.SEARCH_TERMS):
                if test_mode and products_found >= test_limit:
                    break

                async for repos in self._paginate(lambda page: self._fetch_repositories(term, page), respect_test_limit=True):
                    if test_mode and products_found >= test_limit:
                        break

                    for repo in repos:
                        if test_mode and products_found >= test_limit:
                            break

                        products_found += 1

                        # Track which search term matched this repo
                        repo['_matched_search_term'] = term

                        existing = await self._product_exists(repo["html_url"])

                        if existing:
                            result = await self._update_product(existing["id"], repo)
                            if result:
                                products_updated += 1
                        else:
                            result = await self._create_product(repo)
                            if result:
                                products_added += 1

                if test_mode and products_found >= test_limit:
                    break
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                'source': 'GitHub',
                'products_found': products_found,
                'products_added': products_added,
                'products_updated': products_updated,
                'duration_seconds': duration,
                'status': 'success',
            }
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return {
                'source': 'GitHub',
                'products_found': products_found,
                'products_added': products_added,
                'products_updated': products_updated,
                'duration_seconds': duration,
                'status': 'error',
                'error_message': str(e),
            }
    
    async def _fetch_repositories(self, term: str, page: int) -> Tuple[List[Dict[str, Any]], bool]:
        """Fetch one page of repositories from GitHub API for a search term.

        Returns a tuple of (filtered_items, has_more).
        """
        # Don't quote the search term—GitHub's quoted searches are too strict
        # and miss repos where the term is a compound word (e.g., "braille2latex")
        # or has different capitalization (e.g., "Braille" in description).
        # Unquoted search matches the term as word tokens anywhere in repo metadata.
        url = f"{self.API_BASE_URL}/search/repositories"
        params = {
            'q': f'{term} stars:>=3',
            'sort': 'stars',
            'order': 'desc',
            'per_page': self.RESULTS_PER_PAGE,
            'page': page,
        }
        
        try:
            await self._throttle_request()
            response = await self.client.get(
                url,
                params=params,
            )
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            filtered = [item for item in items if not self._is_documentation_only(item)]

            has_more = len(items) >= self.RESULTS_PER_PAGE
            return filtered, has_more
            
        except httpx.HTTPError as e:
            print(f"[GitHub] HTTP Error fetching repositories for term '{term}': {e}")
            return [], False
        except Exception as e:
            print(f"[GitHub] Error fetching repositories for term '{term}': {type(e).__name__}: {e}")
            return [], False
    
    def _is_documentation_only(self, repo: Dict[str, Any]) -> bool:
        """Check if repository is pure documentation (no code)"""
        name = repo.get('name', '').lower()
        description = (repo.get('description') or '').lower()
        
        # Filter out known documentation-only repo patterns
        doc_patterns = ['awesome-', '-list', '-guide', 'guidelines', 'wcag', '-docs', '-l-']
        
        for pattern in doc_patterns:
            if pattern in name:
                return True

        if 'awesome' in description or 'list of' in description or 'curated' in description:
            return True
        if len(name.strip('-')) <= 2:  # extremely short names are likely lists/aggregators
            return True
        
        return False
    
    def _create_product_dict(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """Convert GitHub repo data to product dict"""
        # GitHub doesn't have ratings, but we can use stars as a proxy
        stars = repo.get('stargazers_count', 0)
        
        # Extract topics as tags
        topics = repo.get('topics', [])
        tags = []
        seen = set()
        
        if topics:
            # Deduplicate while preserving order (though topics should already be unique)
            for topic in topics:
                if topic and topic not in seen:
                    seen.add(topic)
                    tags.append(topic)
        
        # Add language as a tag if available
        language = repo.get('language')
        if language and language not in seen:
            tags.append(language)
        
        # Convert stars to a continuous 1–5 rating using a log10 scale.
        # Formula: clamp(log10(stars), 1.0, 5.0)
        # Anchor points: 10→1.0, 100→2.0, 1000→3.0, 10000→4.0, 100000→5.0.
        # Repos with 0 stars receive no rating.
        if stars > 0:
            star_rating = round(min(max(math.log10(stars), 1.0), 5.0), 2)
        else:
            star_rating = None
        
        # Extract last updated timestamp from GitHub
        # GitHub provides both 'updated_at' and 'pushed_at' - use pushed_at as it's more accurate for code changes
        source_last_updated = None
        pushed_at = repo.get('pushed_at') or repo.get('updated_at')
        if pushed_at:
            try:
                # GitHub returns ISO 8601 format: "2024-12-28T12:34:56Z"
                source_last_updated = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
            except Exception as e:
                print(f"[GitHub] Failed to parse last updated date: {e}")
        
        # Track which search term matched (passed via _matched_search_term)
        matched_search_terms = []
        if repo.get('_matched_search_term'):
            matched_search_terms.append(repo['_matched_search_term'])
        
        return {
            'name': repo['name'],
            'description': repo.get('description', ''),
            'url': repo['html_url'],
            'image': repo['owner'].get('avatar_url'),
            'source': 'GitHub',
            'type': 'Software',
            'tags': tags,
            'scraped_at': datetime.now().isoformat(),
            'external_id': str(repo['id']),
            'source_rating': star_rating,  # Normalized star rating (2-5)
            'source_rating_count': stars,  # Actual GitHub star count
            'source_last_updated': source_last_updated.isoformat() if source_last_updated else None,
            'matched_search_terms': matched_search_terms,
            'external_data': {
                'language': language,
                'topics': topics,
            }
        }
    
    async def _create_product(self, repo: Dict[str, Any]) -> bool:
        """Create a new product from GitHub repository"""
        return await super()._create_product(repo)
    
    async def _update_product(self, product_id: str, repo: Dict[str, Any]) -> bool:
        """Update existing product with latest GitHub data"""
        return await super()._update_product(product_id, repo)
