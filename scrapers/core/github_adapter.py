import base64
import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from .base_source_scraper import BaseSourceScraper
from .contracts import RateLimitPolicy, ScrapeRunContext


class GitHubSourceAdapter(BaseSourceScraper):
    """Lean GitHub adapter for the new source-scraper contract."""

    SEARCH_TERMS = [
        "assistive technology",
        "screen reader",
        "eye tracking",
        "speech recognition",
        "switch access",
        "alternative input",
        "text-to-speech",
        "voice control",
        "accessibility aid",
        "mobility aid software",
    ]

    API_BASE_URL = "https://api.github.com"
    RESULTS_PER_PAGE = 20

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
            headers = {"Accept": "application/vnd.github.v3+json"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            self.client = httpx.AsyncClient(headers=headers)

    async def close(self) -> None:
        await self.client.aclose()

    def get_source_name(self) -> str:
        return "github"

    def supports_url(self, url: str) -> bool:
        value = (url or "").lower()
        return "github.com/" in value

    async def enumerate_candidates(self, context: ScrapeRunContext) -> list[dict]:
        collected: list[dict] = []

        for term in self.SEARCH_TERMS:
            page = 1
            while True:
                repos, has_more = await self._fetch_repositories(term=term, page=page)
                if not repos:
                    break

                for repo in repos:
                    if "_matched_search_term" not in repo:
                        repo["_matched_search_term"] = term

                    collected.append(repo)
                    if self.should_stop_collection(len(collected), context):
                        return collected

                if not has_more:
                    break
                page += 1

        return collected

    async def fetch_one(self, candidate: dict, context: ScrapeRunContext) -> dict | None:
        if candidate.get("html_url") and candidate.get("id"):
            return await self._enrich_repo_image_candidates(candidate)

        owner = candidate.get("owner") or {}
        owner_login = owner.get("login")
        repo_name = candidate.get("name")
        if owner_login and repo_name:
            repo = await self._fetch_repo_details(owner_login, repo_name)
            if not repo:
                return None
            return await self._enrich_repo_image_candidates(repo)

        source_url = candidate.get("source_url") or candidate.get("url")
        if not source_url:
            return None

        parts = source_url.rstrip("/").split("/")
        if len(parts) < 5:
            return None
        if "github.com" not in parts[2].lower():
            return None

        repo = await self._fetch_repo_details(parts[3], parts[4])
        if not repo:
            return None
        return await self._enrich_repo_image_candidates(repo)

    def generate_tags(self, raw: dict, source_raw: dict) -> list[str]:
        topics = raw.get("topics") or []
        language = raw.get("language")

        tags: list[str] = []
        seen: set[str] = set()

        for topic in topics:
            value = str(topic).strip()
            if value and value not in seen:
                seen.add(value)
                tags.append(value)

        if language:
            value = str(language).strip()
            if value and value not in seen:
                tags.append(value)

        return tags

    @staticmethod
    def map_stars_to_source_rating(stars: int | None) -> float | None:
        """GitHub star-to-rating mapping.

        Anchor points: 10->1.0, 100->2.0, 1000->3.0, 10000->4.0, 100000->5.0.
        """
        if not stars or stars <= 0:
            return None
        return round(min(max(math.log10(stars), 1.0), 5.0), 2)

    def map_to_source_raw(self, raw: dict, context: ScrapeRunContext) -> dict:
        stars = int(raw.get("stargazers_count") or 0)
        source_rating = self.map_stars_to_source_rating(stars)

        owner = raw.get("owner") or {}
        image_candidates = raw.get("_image_candidates") or []
        preferred_with_alt = next(
            (
                candidate
                for candidate in image_candidates
                if str(candidate.get("url") or "").strip()
                and str(candidate.get("alt") or "").strip()
            ),
            None,
        )

        image_url = None
        image_alt = None
        if preferred_with_alt:
            image_url = str(preferred_with_alt.get("url")).strip()
            image_alt = str(preferred_with_alt.get("alt")).strip()
        else:
            image_url = self.pick_representative_image(
                [
                    *[
                        str(candidate.get("url") or "").strip()
                        for candidate in image_candidates
                        if str(candidate.get("url") or "").strip()
                    ],
                    owner.get("avatar_url"),
                    raw.get("open_graph_image_url"),
                ]
            )

        if image_url and not image_alt:
            image_alt = (
                f"{raw.get('name', 'GitHub repository')} image (ALT text missing on source)"
            )

        source_last_updated = self._parse_source_timestamp(raw)
        matched_search_terms = []
        matched = raw.get("_matched_search_term")
        if matched:
            matched_search_terms.append(str(matched))

        source_url = raw.get("html_url") or raw.get("url")
        if not source_url:
            full_name = raw.get("full_name")
            if full_name:
                source_url = f"https://github.com/{full_name}"
            else:
                source_url = "https://github.com"

        return {
            "source": self.get_source_name(),
            "external_id": str(raw.get("id") or raw.get("node_id") or source_url),
            "source_url": source_url,
            "name": raw.get("name") or raw.get("full_name") or "github-repo",
            "description": raw.get("description") or "",
            "source_last_updated": source_last_updated,
            "matched_search_terms": matched_search_terms,
            "tags": self.generate_tags(raw, {}),
            "image_url": image_url,
            "image_alt": image_alt,
            "source_rating": source_rating,
            "source_rating_count": stars,
            "external_data": {
                "language": raw.get("language"),
                "topics": raw.get("topics") or [],
            },
        }

    async def _enrich_repo_image_candidates(self, repo: dict[str, Any]) -> dict[str, Any]:
        owner = repo.get("owner") or {}
        owner_login = owner.get("login")
        repo_name = repo.get("name")
        if not owner_login or not repo_name:
            return repo

        default_branch = repo.get("default_branch") or "main"
        readme_images = await self._fetch_readme_images(owner_login, repo_name, default_branch)
        if readme_images:
            enriched = dict(repo)
            enriched["_image_candidates"] = readme_images
            return enriched

        return repo

    async def _fetch_readme_images(
        self, owner: str, repo: str, default_branch: str
    ) -> list[dict[str, str]]:
        try:
            response = await self.client.get(
                f"{self.API_BASE_URL}/repos/{owner}/{repo}/readme",
                headers={"Accept": "application/vnd.github+json"},
                timeout=10.0,
            )
            if response.status_code != 200:
                return []

            payload = response.json()
            if payload.get("encoding") != "base64":
                return []

            content = payload.get("content") or ""
            readme_text = base64.b64decode(content).decode("utf-8", errors="ignore")
            readme_path = str(payload.get("path") or "README.md")
            return self._extract_readme_images(
                readme_text,
                owner=owner,
                repo=repo,
                default_branch=default_branch,
                readme_path=readme_path,
            )
        except Exception:
            return []

    def _extract_readme_images(
        self,
        markdown_text: str,
        *,
        owner: str,
        repo: str,
        default_branch: str,
        readme_path: str,
    ) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []

        markdown_pattern = re.compile(
            r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
        )
        html_pattern = re.compile(r"<img\s+[^>]*>", flags=re.IGNORECASE)
        src_pattern = re.compile(r"src\s*=\s*['\"](?P<src>[^'\"]+)['\"]", flags=re.IGNORECASE)
        alt_pattern = re.compile(r"alt\s*=\s*['\"](?P<alt>[^'\"]*)['\"]", flags=re.IGNORECASE)

        for match in markdown_pattern.finditer(markdown_text):
            raw_url = (match.group("url") or "").strip()
            alt = (match.group("alt") or "").strip()
            resolved = self._resolve_readme_image_url(
                raw_url,
                owner=owner,
                repo=repo,
                default_branch=default_branch,
                readme_path=readme_path,
            )
            if resolved:
                candidates.append({"url": resolved, "alt": alt})

        for img_match in html_pattern.finditer(markdown_text):
            img_tag = img_match.group(0)
            src_match = src_pattern.search(img_tag)
            if not src_match:
                continue

            raw_url = (src_match.group("src") or "").strip()
            alt_match = alt_pattern.search(img_tag)
            alt = (alt_match.group("alt") or "").strip() if alt_match else ""
            resolved = self._resolve_readme_image_url(
                raw_url,
                owner=owner,
                repo=repo,
                default_branch=default_branch,
                readme_path=readme_path,
            )
            if resolved:
                candidates.append({"url": resolved, "alt": alt})

        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for candidate in candidates:
            url = candidate.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(candidate)

        return deduped

    def _resolve_readme_image_url(
        self,
        raw_url: str,
        *,
        owner: str,
        repo: str,
        default_branch: str,
        readme_path: str,
    ) -> str | None:
        value = (raw_url or "").strip()
        if not value:
            return None
        if value.startswith(("data:", "mailto:", "#")):
            return None
        if value.startswith("//"):
            return f"https:{value}"

        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            return value

        readme_dir = ""
        if "/" in readme_path:
            readme_dir = readme_path.rsplit("/", 1)[0].strip("/")

        if value.startswith("/"):
            relative_path = value.lstrip("/")
        elif readme_dir:
            relative_path = f"{readme_dir}/{value}"
        else:
            relative_path = value

        return f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{relative_path}"

    async def _fetch_repo_details(self, owner: str, repo: str) -> dict[str, Any] | None:
        try:
            response = await self.client.get(
                f"{self.API_BASE_URL}/repos/{owner}/{repo}",
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            return None
        return None

    async def _fetch_repositories(self, term: str, page: int) -> tuple[list[dict], bool]:
        params = {
            "q": f"{term} stars:>=3",
            "sort": "stars",
            "order": "desc",
            "per_page": self.RESULTS_PER_PAGE,
            "page": page,
        }

        try:
            response = await self.client.get(
                f"{self.API_BASE_URL}/search/repositories",
                params=params,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            has_more = len(items) >= self.RESULTS_PER_PAGE
            return items, has_more
        except Exception:
            return [], False

    def _parse_source_timestamp(self, raw: dict) -> str | None:
        pushed_at = raw.get("pushed_at") or raw.get("updated_at")
        if not pushed_at:
            return None

        try:
            parsed = datetime.fromisoformat(str(pushed_at).replace("Z", "+00:00"))
            return parsed.astimezone(UTC).isoformat()
        except Exception:
            return None
