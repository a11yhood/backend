from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BlogPostBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=200)
    content: str = Field(..., min_length=1)
    excerpt: str | None = Field(None, max_length=1000)
    header_image: str | None = None
    header_image_alt: str | None = Field(None, max_length=300)
    tags: list[str] = Field(default_factory=list)
    featured: bool = False
    published: bool = False
    publish_date: datetime | None = None
    published_at: datetime | None = None
    author_ids: list[str] | None = None
    author_names: list[str] | None = None


class BlogPostCreate(BlogPostBase):
    author_id: str = Field(..., min_length=1)
    author_name: str = Field(..., min_length=1)


class BlogPostUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    content: str | None = None
    excerpt: str | None = None
    header_image: str | None = None
    header_image_alt: str | None = None
    tags: list[str] | None = None
    featured: bool | None = None
    published: bool | None = None
    publish_date: datetime | None = None
    published_at: datetime | None = None
    author_id: str | None = None
    author_name: str | None = None
    author_ids: list[str] | None = None
    author_names: list[str] | None = None


class BlogPostResponse(BlogPostBase):
    id: str
    author_id: str
    author_name: str
    created_at: str  # ISO 8601 UTC datetime string
    updated_at: str  # ISO 8601 UTC datetime string
    publish_date: str | None = None  # type: ignore[assignment]  # ISO 8601 UTC
    published_at: str | None = None  # type: ignore[assignment]  # ISO 8601 UTC

    model_config = ConfigDict(from_attributes=True)
