"""
User activity models for tracking user actions.
"""

from datetime import datetime

from pydantic import BaseModel


class UserActivityCreate(BaseModel):
    """Request model for creating user activity"""

    user_id: str
    type: str  # 'product_submit' | 'rating' | 'discussion' | 'tag'
    product_id: str | None = None
    timestamp: datetime  # ISO 8601 string; Pydantic coerces and validates
    metadata: dict | None = None


class UserActivityResponse(BaseModel):
    """Response model for user activity"""

    id: str
    user_id: str
    type: str
    product_id: str | None = None
    timestamp: str  # ISO 8601 UTC datetime string
    created_at: str | None = None
    metadata: dict | None = None
