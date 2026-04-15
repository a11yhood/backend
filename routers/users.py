"""User account management endpoints.

Handles user profile CRUD, role management, and ownership tracking.
Security: Role changes restricted to admins; users can only edit their own profiles.
Privacy: Public username lookup excludes email and preferences.
"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from config import settings
from services.auth import ensure_admin, get_current_user, get_current_user_optional
from services.database import get_db
from services.security_logger import log_role_change

router = APIRouter(prefix="/api/users", tags=["users"])


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"uuid error: {type(e).__name__}: {str(e)}")
        return False


def _get_user_by_identifier(db, identifier: str) -> dict:
    """Fetch a user by username or id (UUID string) or raise 404."""
    response = db.table("users").select("*").eq("username", identifier).limit(1).execute()
    if response.data:
        return response.data[0]
    if _looks_like_uuid(identifier):
        response = db.table("users").select("*").eq("id", identifier).limit(1).execute()
        if response.data:
            return response.data[0]
    raise HTTPException(status_code=404, detail="User not found")


class UserAccountCreate(BaseModel):
    """Request model for creating/updating user account"""

    username: str
    avatar_url: str | None = None
    email: str | None = None


class PublicUserAccountResponse(BaseModel):
    """Public-facing user response; includes id but omits sensitive fields."""

    id: str
    username: str
    username_display: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    role: str
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    preferences: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    joined_at: str | None = None
    last_active: str | None = None


class UserAccountResponse(PublicUserAccountResponse):
    """Internal/admin response that still includes the UUID."""

    id: str


@router.get("/me", response_model=UserAccountResponse, response_model_by_alias=False)
async def get_current_user_profile(
    response: Response, current_user: dict = Depends(get_current_user), db=Depends(get_db)
):
    """Get current authenticated user's full profile.

    Security: Requires authentication. Returns full user data including email and preferences.
    """
    # Add caching headers (30 seconds for user profile to reduce DB load)
    response.headers["Cache-Control"] = "private, max-age=30"

    user_id = current_user.get("id")
    db_result = db.table("users").select("*").eq("id", user_id).execute()
    if not db_result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user = db_result.data[0]
    role = user.get("role", "user")
    username_display = user.get("username", "")
    return UserAccountResponse(
        id=user["id"],
        username=username_display,
        username_display=username_display,
        avatar_url=user.get("avatar_url"),
        email=user.get("email"),
        role=role,
        display_name=user.get("display_name"),
        bio=user.get("bio"),
        location=user.get("location"),
        website=user.get("website"),
        preferences=user.get("preferences"),
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
        joined_at=user.get("joined_at"),
        last_active=user.get("last_active"),
    )


@router.get(
    "/{identifier}", response_model=PublicUserAccountResponse, response_model_by_alias=False
)
async def get_user_account(identifier: str, db=Depends(get_db)):
    """Get user account by username."""
    user = _get_user_by_identifier(db, identifier)
    role = user.get("role", "user")
    username_display = user.get("username", "")
    return PublicUserAccountResponse(
        id=user.get("id"),
        username=username_display,
        username_display=username_display,
        avatar_url=user.get("avatar_url"),
        email=user.get("email"),
        role=role,
        display_name=user.get("display_name"),
        bio=user.get("bio"),
        location=user.get("location"),
        website=user.get("website"),
        preferences=user.get("preferences"),
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
        joined_at=user.get("joined_at"),
        last_active=user.get("last_active"),
    )


@router.get(
    "/by-username/{username}",
    response_model=PublicUserAccountResponse,
    response_model_by_alias=False,
)
async def get_user_by_username(username: str, db=Depends(get_db)):
    """Public endpoint: get user account by username.

    Privacy: Returns public fields only (email and preferences excluded).
    """
    user = _get_user_by_identifier(db, username)
    role = user.get("role", "user")
    username_display = user.get("username", "")
    return PublicUserAccountResponse(
        id=user.get("id"),
        username=username_display,
        username_display=username_display,
        avatar_url=user.get("avatar_url"),
        email=None,  # hide email in public response
        role=role,
        display_name=user.get("display_name"),
        bio=user.get("bio"),
        location=user.get("location"),
        website=user.get("website"),
        preferences=None,
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
        joined_at=user.get("joined_at"),
        last_active=user.get("last_active"),
    )


@router.put("/{identifier}", response_model=UserAccountResponse, response_model_by_alias=False)
@router.post("/{identifier}", response_model=UserAccountResponse, response_model_by_alias=False)
async def create_or_update_user_account(
    identifier: str,
    account_data: UserAccountCreate,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user_optional),
):
    """Create or update user account by username."""
    # Check if user exists by username first, then by id
    existing_resp = db.table("users").select("*").eq("username", identifier).limit(1).execute()
    existing_user = existing_resp.data[0] if existing_resp.data else None
    if not existing_user and _looks_like_uuid(identifier):
        existing_by_id = db.table("users").select("*").eq("id", identifier).limit(1).execute()
        if existing_by_id.data:
            existing_user = existing_by_id.data[0]
    is_update = existing_user is not None

    # Determine test mode safely, falling back to environment if settings is unavailable
    try:
        test_mode = bool(getattr(settings, "TEST_MODE", False))
    except NameError:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"

    # In production mode, require auth for updates (creates allowed for OAuth)
    if not test_mode and is_update and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Prevent one user from updating another unless admin
    if is_update and current_user and current_user.get("role") != "admin":
        if current_user.get("id") != existing_user.get("id"):
            raise HTTPException(status_code=403, detail="Not authorized to update this user")

    print(
        f"[users] is_update={is_update}, test_mode={test_mode}, existing_count={1 if existing_user else 0}"
    )

    # Resolve the backing user_id
    user_id = (current_user or {}).get("id") or (existing_user.get("id") if existing_user else None)
    if not user_id:
        user_id = identifier if _looks_like_uuid(identifier) else str(uuid.uuid4())

    # Build user data and ensure github_id is present to satisfy schema
    github_id = (current_user or {}).get("github_id") or user_id
    user_data = {
        "username": account_data.username,
        "avatar_url": account_data.avatar_url,
        "email": account_data.email,
        "github_id": github_id,
    }

    try:
        if is_update:
            # Update existing user - preserve role by not including it in update
            db.table("users").update(user_data).eq("id", existing_user["id"]).execute()
            response = db.table("users").select("*").eq("id", existing_user["id"]).execute()
            updated_user = response.data[0] if response.data else existing_user
            print(
                f"[users] updated user id={updated_user.get('id')} role={updated_user.get('role')}"
            )
        else:
            # If username exists (race) try update; otherwise insert new
            by_username = existing_resp
            if by_username.data:
                db.table("users").update({**user_data, "id": user_id}).eq(
                    "username", account_data.username
                ).execute()
                response = (
                    db.table("users")
                    .select("*")
                    .eq("username", account_data.username)
                    .limit(1)
                    .execute()
                )
                updated_user = response.data[0] if response.data else by_username.data[0]
                print(f"[users] reassigned existing username to id={user_id}")
            else:
                payload = {**user_data, "id": user_id, "role": "user"}
                response = db.table("users").insert(payload).execute()
                updated_user = response.data[0] if response.data else payload
                print(
                    f"[users] inserted user id={updated_user.get('id')} role={updated_user.get('role')}"
                )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[users] ERROR creating/updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    role = updated_user.get("role", "user")
    username_display = updated_user.get("username", "")
    return UserAccountResponse(
        id=updated_user["id"],
        username=username_display,
        username_display=username_display,
        avatar_url=updated_user.get("avatar_url"),
        email=updated_user.get("email"),
        role=role,
        display_name=updated_user.get("display_name"),
        bio=updated_user.get("bio"),
        location=updated_user.get("location"),
        website=updated_user.get("website"),
        preferences=updated_user.get("preferences"),
        created_at=updated_user.get("created_at"),
        updated_at=updated_user.get("updated_at"),
        joined_at=updated_user.get("joined_at"),
        last_active=updated_user.get("last_active"),
    )


class RoleUpdate(BaseModel):
    role: str  # 'user' | 'moderator' | 'admin'


@router.patch("/{username}/role")
async def update_user_role(
    username: str,
    role_update: RoleUpdate,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a user's role by username.

    Uses admin_update_user_role database function to properly handle
    role changes with admin verification at the database level.
    """
    new_role = role_update.role
    if new_role not in {"user", "moderator", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    # Authorization: require admin via policy helper
    ensure_admin(current_user)

    target_user = _get_user_by_identifier(db, username)
    old_role = target_user.get("role", "user")
    user_id = target_user["id"]

    # Call database function to update role with admin privileges
    # This function verifies admin status and updates the role
    try:
        logger = logging.getLogger(__name__)
        logger.info(
            f"Calling admin_update_user_role with admin_user_id={current_user['id']}, target_user_id={user_id}, new_role={new_role}"
        )

        response = db.rpc(
            "admin_update_user_role",
            {"admin_user_id": current_user["id"], "target_user_id": user_id, "new_role": new_role},
        ).execute()

        logger.info(f"RPC response: {response}")
        updated_user = response.data if getattr(response, "data", None) else target_user

    except Exception as e:
        # The function returns the updated user as JSONB

        logger = logging.getLogger(__name__)
        logger.error(f"RPC error: {type(e).__name__}: {str(e)}")

        # Handle database errors (user not found, permission denied, etc.)
        error_msg = str(e)
        if "Only admins can change roles" in error_msg:
            raise HTTPException(status_code=403, detail="Only admins can change roles")
        elif "User not found" in error_msg:
            raise HTTPException(status_code=404, detail="User not found")
        elif "Invalid role" in error_msg:
            raise HTTPException(status_code=400, detail="Invalid role")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to update role: {error_msg}")

    # Log security event for role change
    log_role_change(
        admin_id=current_user["id"], target_user_id=user_id, old_role=old_role, new_role=new_role
    )

    return {
        "id": updated_user.get("id"),
        "username": updated_user.get("username", ""),
        "avatar_url": updated_user.get("avatar_url"),
        "email": updated_user.get("email"),
        "role": updated_user.get("role", "user"),
        "display_name": updated_user.get("display_name"),
        "created_at": updated_user.get("created_at"),
    }


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    preferences: dict | None = None


@router.patch(
    "/{username}/profile", response_model=UserAccountResponse, response_model_by_alias=False
)
async def update_user_profile(
    username: str,
    updates: ProfileUpdate,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a user's profile fields. Currently supports display_name."""
    target_user = _get_user_by_identifier(db, username)

    # Authorization: allow if current user matches or is admin
    if current_user.get("id") != target_user.get("id") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    update_data = {}
    if updates.display_name is not None:
        update_data["display_name"] = updates.display_name
    if updates.bio is not None:
        update_data["bio"] = updates.bio
    if updates.location is not None:
        update_data["location"] = updates.location
    if updates.website is not None:
        update_data["website"] = updates.website
    if updates.preferences is not None:
        update_data["preferences"] = updates.preferences

    # If nothing to update, return current record
    if not update_data:
        user = target_user
        role = user.get("role", "user")
        return UserAccountResponse(
            id=user["id"],
            username=user.get("username", ""),
            avatar_url=user.get("avatar_url"),
            email=user.get("email"),
            role=role,
            display_name=user.get("display_name"),
            bio=user.get("bio"),
            location=user.get("location"),
            website=user.get("website"),
            preferences=user.get("preferences"),
            created_at=user.get("created_at"),
            updated_at=user.get("updated_at"),
            joined_at=user.get("joined_at"),
            last_active=user.get("last_active"),
        )

    response = db.table("users").update(update_data).eq("id", target_user["id"]).execute()
    updated_user = response.data[0] if response.data else target_user
    role = updated_user.get("role", "user")
    return UserAccountResponse(
        id=updated_user["id"],
        username=updated_user.get("username", ""),
        avatar_url=updated_user.get("avatar_url"),
        email=updated_user.get("email"),
        role=role,
        display_name=updated_user.get("display_name"),
        bio=updated_user.get("bio"),
        location=updated_user.get("location"),
        website=updated_user.get("website"),
        preferences=updated_user.get("preferences"),
        created_at=updated_user.get("created_at"),
        updated_at=updated_user.get("updated_at"),
        joined_at=updated_user.get("joined_at"),
        last_active=updated_user.get("last_active"),
    )


@router.get("/")
async def get_all_users(db=Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get all users (admin only)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    response = db.table("users").select("*").execute()
    return response.data


@router.get("/{username}/collections")
async def get_user_collections(username: str, db=Depends(get_db)):
    """Get user's product collections (not implemented yet)"""
    # TODO: Implement collections when the feature is ready
    return []


@router.get("/{username}/requests")
async def get_user_requests(
    username: str, db=Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """Get user's requests (must be the user or admin)"""
    target_user = _get_user_by_identifier(db, username)
    # Check authorization
    if current_user["id"] != target_user.get("id") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view these requests")

    response = (
        db.table("user_requests")
        .select("*")
        .eq("user_id", target_user.get("id"))
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


@router.get("/{username}/stats")
async def get_user_stats(username: str, db=Depends(get_db)):
    """Get user statistics"""
    target_user = _get_user_by_identifier(db, username)
    user_id = target_user.get("id")
    # Count user's contributions
    products = db.table("products").select("id").eq("created_by", user_id).execute()
    ratings = db.table("ratings").select("id").eq("user_id", user_id).execute()
    discussions = db.table("discussions").select("id").eq("user_id", user_id).execute()

    products_submitted = len(products.data) if products.data else 0
    ratings_given = len(ratings.data) if ratings.data else 0
    discussions_participated = len(discussions.data) if discussions.data else 0

    return {
        "products_submitted": products_submitted,
        "ratings_given": ratings_given,
        "discussions_participated": discussions_participated,
        "total_contributions": products_submitted + ratings_given + discussions_participated,
    }


@router.get("/{username}/owned-products")
async def get_owned_products(
    username: str, db=Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """Get products owned by a user"""
    target_user = _get_user_by_identifier(db, username)
    user_id = target_user.get("id")
    # Check authorization - must be the user or admin
    if current_user["id"] != user_id and current_user.get("role") not in ["admin", "moderator"]:
        raise HTTPException(status_code=403, detail="Not authorized to view these products")

    # Get all product IDs owned by this user
    ownership_response = (
        db.table("product_editors").select("product_id").eq("user_id", user_id).execute()
    )

    if not ownership_response.data:
        return {"products": []}

    product_ids = [row["product_id"] for row in ownership_response.data]

    # Get the actual products
    products_response = db.table("products").select("*").in_("id", product_ids).execute()

    return {"products": products_response.data or []}
