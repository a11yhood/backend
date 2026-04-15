"""User account Pydantic models for request/response validation.

Defines schemas for user CRUD operations with role management.
Email validation enforced via EmailStr for security.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    products_owned: list[str] | None = None
    role: str | None = None


class UserResponse(UserBase):
    id: str
    products_owned: list[str] = []
    role: str = "user"
    created_at: datetime
    updated_at: datetime
    username_display: str | None = None

    class Config:
        from_attributes = True


class UserProfile(UserResponse):
    """Extended user profile with statistics"""

    ratings_count: int | None = None
    discussions_count: int | None = None
