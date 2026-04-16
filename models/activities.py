"""
User activity models for tracking user actions.
"""

from datetime import datetime

from pydantic import BaseModel

from services.timestamps import ApiTimestamp, OptionalApiTimestamp


class UserActivityCreate(BaseModel):
    """Request model for creating user activity"""

    user_id: str
    type: str  # 'product_submit' | 'rating' | 'discussion' | 'tag'
    product_id: str | None = None
    timestamp: ApiTimestamp
    metadata: dict | None = None


class UserActivityResponse(BaseModel):
    """Response model for user activity"""

    id: str
    user_id: str
    type: str
    product_id: str | None = None
    timestamp: ApiTimestamp
    created_at: OptionalApiTimestamp = None
    metadata: dict | None = None
