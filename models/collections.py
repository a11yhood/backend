from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_public: bool = Field(default=True)


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_public: bool | None = None


class ProductIdsRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)


class CollectionFromSearchCreate(CollectionBase):
    """Create a collection from search results."""

    source: list[str] | None = Field(None, description="Source filter for search")
    sources: list[str] | None = Field(None, description="Source filter for search")
    type: list[str] | None = Field(None, description="Type filter for search")
    types: list[str] | None = Field(None, description="Type filter for search")
    tags: list[str] | None = Field(None, description="Tag filter for search")
    tags_mode: str = Field(
        default="or", pattern=r"^(?i)(or|and)$", description="Tag filter mode: or or and"
    )
    search: str | None = Field(None, description="Text search on product name")
    min_rating: float | None = Field(None, ge=0, le=5, description="Minimum rating filter")


class CollectionResponse(CollectionBase):
    id: str
    slug: str
    user_id: str
    user_name: str
    product_ids: list[str] = Field(default_factory=list)
    product_slugs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
