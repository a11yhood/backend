from datetime import datetime

from pydantic import BaseModel, Field


class SupportedSourceBase(BaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(
        None, description="Markdown-formatted description of the source"
    )


class SupportedSourceCreate(SupportedSourceBase):
    pass


class SupportedSourceUpdate(BaseModel):
    domain: str | None = Field(None, min_length=1, max_length=255)
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(
        None, description="Markdown-formatted description of the source"
    )


class SupportedSourceResponse(SupportedSourceBase):
    id: str
    created_at: datetime
    updated_at: datetime
