"""
User activity models for tracking user actions.
"""

from pydantic import BaseModel


class UserActivityCreate(BaseModel):
    """Request model for creating user activity"""

    user_id: str
    type: str  # 'product_submit' | 'rating' | 'discussion' | 'tag'
    product_id: str | None = None
    timestamp: int  # milliseconds since epoch
    metadata: dict | None = None


class UserActivityResponse(BaseModel):
    """Response model for user activity"""

    id: str
    user_id: str
    type: str
    product_id: str | None = None
    timestamp: int
    created_at: str | None = None
    metadata: dict | None = None
