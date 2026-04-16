from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from services.timestamps import ApiTimestamp, OptionalApiTimestamp


class DiscussionBase(BaseModel):
    product_id: str
    content: str = Field(..., min_length=1)
    parent_id: str | None = None


class DiscussionCreate(DiscussionBase):
    pass


class DiscussionUpdate(BaseModel):
    content: str | None = Field(None, min_length=1)


class DiscussionBlockRequest(BaseModel):
    reason: str | None = None


class DiscussionResponse(DiscussionBase):
    id: str
    user_id: str
    username: str
    created_at: ApiTimestamp
    updated_at: ApiTimestamp
    blocked: bool = False
    blocked_by: str | None = None
    blocked_reason: str | None = None
    blocked_at: OptionalApiTimestamp = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
