from pydantic import BaseModel, Field, field_validator


class ProductQueryDefinition(BaseModel):
    source: list[str] | None = Field(None, description="Source filter for search")
    sources: list[str] | None = Field(None, description="Source filter for search")
    type: list[str] | None = Field(None, description="Type filter for search")
    types: list[str] | None = Field(None, description="Type filter for search")
    tags: list[str] | None = Field(None, description="Tag filter for search")
    tags_mode: str = Field(
        default="or", pattern=r"^(?i)(or|and)$", description="Tag filter mode: or or and"
    )
    min_rating: float | None = Field(None, ge=0, le=5, description="Minimum rating filter")
    updated_since: str | None = Field(
        None, description="Filter products updated at source since this date (ISO format)"
    )
    max_age: int | None = Field(None, description="Filter products updated in the last N days")
    search: str | None = Field(None, description="Text search on product name")
    created_by: str | None = Field(None, description="Filter products by creator user ID")
    editor_id: str | None = Field(None, description="Filter products by editor user ID")
    include_banned: bool = Field(
        default=False, description="Include banned products (admin/mod only)"
    )

    @field_validator("source", "sources", "type", "types", "tags", mode="before")
    @classmethod
    def _coerce_scalar_to_list(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            return [value]
        return value


class BulkDeleteRequest(ProductQueryDefinition):
    product_ids: str | list[str] | None = None
