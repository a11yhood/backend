from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ScrapeMode(StrEnum):
    QUICK_CHECK_ONLY = "quick_check_only"
    SINGLE_PRODUCT = "single_product"
    FULL_SOURCE = "full_source"
    FULL_SOURCE_TEST_N = "full_source_test_n"


class AuthorizationStrategy(StrEnum):
    OAUTH2_REFRESHABLE = "oauth2_refreshable"
    BEARER_TOKEN = "bearer_token"
    STATIC_HEADER = "static_header"
    NONE = "none"


class PersistOutcome(StrEnum):
    ADDED = "added"
    UPDATED = "updated"
    SKIPPED_EXISTING = "skipped_existing"
    FAILED_VALIDATION = "failed_validation"
    FAILED_PERSIST = "failed_persist"


@dataclass(slots=True)
class RateLimitPolicy:
    requests_per_minute: int
    burst_size: int | None = None
    jitter_ms: int | None = None
    retry_backoff_profile: str = "exponential"


@dataclass(slots=True)
class ScrapeRunContext:
    mode: ScrapeMode
    matched_search_terms: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expected_max_rating: float | None = None
    max_products: int | None = None


@dataclass(slots=True)
class SourceScrapedProduct:
    source: str
    external_id: str
    source_url: str
    name: str
    description: str | None
    source_last_updated: str | None
    matched_search_terms: list[str]
    tags: list[str]
    image_url: str | None
    image_alt: str | None
    source_rating: float | None
    source_rating_count: int | None
    external_data: dict[str, Any]
    fetched_at: str
    scrape_mode: str
