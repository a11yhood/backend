from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RatingBase(BaseModel):
    product_id: str
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")


class RatingCreate(RatingBase):
    pass


class RatingUpdate(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)


class RatingResponse(RatingBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
