
from pydantic import BaseModel, ConfigDict, Field

from services.timestamps import ApiTimestamp


class ScrapingLogBase(BaseModel):
    source: str
    products_found: int
    products_added: int
    products_updated: int
    duration_seconds: float
    status: str  # 'success', 'error', 'halted'
    error_message: str | None = None


class ScrapingLogCreate(ScrapingLogBase):
    pass


class ScrapingLogResponse(ScrapingLogBase):
    id: str
    user_id: str
    created_at: ApiTimestamp

    model_config = ConfigDict(from_attributes=True)


class OAuthConfigBase(BaseModel):
    platform: str  # 'ravelry', 'thingiverse', 'github'
    client_id: str
    client_secret: str
    redirect_uri: str


class OAuthConfigCreate(OAuthConfigBase):
    pass


class OAuthConfigUpdate(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


class OAuthConfigResponse(BaseModel):
    id: str
    platform: str
    client_id: str
    redirect_uri: str
    created_at: ApiTimestamp
    updated_at: ApiTimestamp
    # client_secret is intentionally excluded for security

    model_config = ConfigDict(from_attributes=True)


from enum import StrEnum


class ScraperSource(StrEnum):
    """Valid scraper sources"""

    thingiverse = "thingiverse"
    ravelry = "ravelry"
    github = "github"
    goat = "goat"


class ScraperTriggerRequest(BaseModel):
    source: ScraperSource = Field(
        ..., description="Platform to scrape: 'thingiverse', 'ravelry', 'github', 'goat'"
    )
    test_mode: bool = Field(False, description="If true, only scrape limited items for testing")
    test_limit: int = Field(5, description="Number of items to scrape in test mode", ge=1, le=50)
