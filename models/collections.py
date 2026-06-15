
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from models.product_queries import ProductQueryDefinition
from services.timestamps import ApiTimestamp


class CollectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_public: bool = Field(default=True)


class CollectionCreate(CollectionBase):
    entries: list["CollectionEntry"] | None = None


class CollectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_public: bool | None = None
    entries: list["CollectionEntry"] | None = None


class ProductIdsRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)


class CollectionEditorsResponse(BaseModel):
    collection_id: str
    editor_ids: list[str] = Field(default_factory=list)


class CollectionFromSearchCreate(CollectionBase, ProductQueryDefinition):
    """Create a collection from search results."""


class CollectionEntryBase(BaseModel):
    kind: Literal["product", "collection", "blogPost", "query"]
    position: int = Field(default=0, ge=0)
    label: str | None = Field(default=None, max_length=255)


class ProductCollectionEntry(CollectionEntryBase):
    kind: Literal["product"]
    product_id: str


class NestedCollectionEntry(CollectionEntryBase):
    kind: Literal["collection"]
    collection_id: str


class BlogPostCollectionEntry(CollectionEntryBase):
    kind: Literal["blogPost"]
    blog_post_id: str


class QueryCollectionEntry(CollectionEntryBase):
    kind: Literal["query"]
    query: ProductQueryDefinition


CollectionEntry = Annotated[
    ProductCollectionEntry | NestedCollectionEntry | BlogPostCollectionEntry | QueryCollectionEntry,
    Field(discriminator="kind"),
]


class CollectionResponse(CollectionBase):
    id: str
    slug: str
    user_id: str
    user_name: str
    editor_ids: list[str] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)
    product_slugs: list[str] = Field(default_factory=list)
    entries: list[CollectionEntry] = Field(default_factory=list)
    access_role: str | None = Field(
        default=None,
        description="Authenticated access role for this collection (`owner` or `editor`) when context applies.",
    )
    is_owner: bool | None = Field(
        default=None,
        description="Whether the authenticated user is the collection owner when context applies.",
    )
    created_at: ApiTimestamp
    updated_at: ApiTimestamp

    model_config = ConfigDict(from_attributes=True)
