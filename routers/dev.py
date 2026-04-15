"""Dev mode API endpoints - only available in TEST_MODE.

Provides:
- GET /api/dev/stats - Table statistics
- POST /api/dev/reset - Clear all data
- Health check specific to dev
- POST /api/dev/test-auth/login - deterministic test auth for exact user identity
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from config import load_settings_from_env
from services.auth import VALID_DEV_ROLES
from services.auth import ensure_admin, get_current_user
from services.database import get_db
from services.dev_mode import enforce_dev_row_limits, get_dev_stats, reset_database

router = APIRouter(prefix="/api/dev", tags=["dev"])


class DevTestAuthLoginRequest(BaseModel):
    """Identity-bound test login request for frontend integration tests."""

    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    create_if_missing: bool = False
    role: str = "user"
    display_name: str | None = None


class DevTestAuthLoginResponse(BaseModel):
    """Response with deterministic dev token bound to one exact user ID."""

    access_token: str
    token_type: str = "Bearer"
    user: dict
    created: bool = False


def _require_dev_mode():
    """Verify dev mode is enabled."""
    settings = load_settings_from_env()
    if not settings.TEST_MODE:
        raise HTTPException(status_code=404, detail="Dev endpoints not available outside TEST_MODE")


def _require_dev_test_auth_secret(x_test_auth_secret: str | None):
    """Require optional shared secret when configured for test-auth endpoint."""
    configured_secret = load_settings_from_env().DEV_TEST_AUTH_SECRET
    if configured_secret and x_test_auth_secret != configured_secret:
        raise HTTPException(status_code=403, detail="Invalid test auth secret")


def _resolve_test_auth_user(db, payload: DevTestAuthLoginRequest):
    """Resolve a user by id/username/email in deterministic order."""
    if payload.user_id:
        resp = db.table("users").select("*").eq("id", payload.user_id).limit(1).execute()
        if resp.data:
            return resp.data[0]

    if payload.username:
        resp = db.table("users").select("*").eq("username", payload.username).limit(1).execute()
        if resp.data:
            return resp.data[0]

    if payload.email:
        resp = db.table("users").select("*").eq("email", payload.email).limit(1).execute()
        if resp.data:
            return resp.data[0]

    return None


def _create_test_auth_user(db, payload: DevTestAuthLoginRequest):
    """Create a deterministic test user for identity-bound auth flows."""
    role = (payload.role or "user").strip().lower()
    if role not in VALID_DEV_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Valid: {', '.join(sorted(VALID_DEV_ROLES))}",
        )

    user_id = payload.user_id or str(uuid.uuid4())
    username = payload.username or f"test_user_{user_id[:8]}"
    email = payload.email or f"{username}@a11yhood.test"
    display_name = payload.display_name or username

    new_user = {
        "id": user_id,
        "github_id": f"dev-test-{user_id}",
        "username": username,
        "display_name": display_name,
        "email": email,
        "role": role,
    }

    try:
        created = db.table("users").insert(new_user).execute()
        if created.data:
            return created.data[0]
        return new_user
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create test user: {exc}")


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    """Get dev mode statistics (admin only).

    Returns:
        - mode: "dev"
        - max_rows_per_table: configured limit
        - scrapers_disabled: whether scheduled scrapers are off
        - test_scraper_limit: max products per scraper run
        - tables: dict of {table_name: {rows: int, at_limit: bool}}
    """
    _require_dev_mode()
    ensure_admin(current_user)

    return await get_dev_stats()


@router.post("/reset")
async def reset_db(current_user: dict = Depends(get_current_user)):
    """
    ⚠️ DANGEROUS: Reset database to clean state.

    - Clears ALL user-created data
    - Only available in dev mode + admin role
    - Does NOT reseed (manually run seed script after)

    Use cases:
    - Cleanup after messy testing
    - Before automated test runs
    - Reset when making schema changes

    Admin only.

    Returns:
        - status: "reset"
        - cleared_tables: dict of {table_name: rows_deleted}
        - total_rows_deleted: int
    """
    _require_dev_mode()
    ensure_admin(current_user)

    return await reset_database()


@router.get("/check-limits")
async def check_limits(current_user: dict = Depends(get_current_user)):
    """
    Check if any table exceeds dev row limits.

    Returns 200 if all tables are within limits.
    Returns 400 with details if any table exceeds limit.

    Admin only.
    """
    _require_dev_mode()
    ensure_admin(current_user)

    try:
        await enforce_dev_row_limits()
        return {"status": "ok", "message": "All tables within dev limits"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health-dev")
async def health_dev():
    """Dev-specific health check - no auth required.

    Confirms:
    - Dev mode is enabled
    - Dev endpoints are available

    Always returns 200 in dev mode.
    """
    _require_dev_mode()
    return {"status": "healthy", "mode": "dev", "message": "Dev mode active - endpoints available"}


@router.post("/test-auth/login", response_model=DevTestAuthLoginResponse)
async def test_auth_login(
    payload: DevTestAuthLoginRequest,
    x_test_auth_secret: str | None = Header(default=None, alias="X-Test-Auth-Secret"),
    db=Depends(get_db),
):
    """Resolve or create a user and return a UUID-based dev token for exact identity auth.

    This endpoint is only available in TEST_MODE and returns a token in the
    existing format expected by get_current_user: ``dev-token-<user_id>``.
    """
    _require_dev_mode()
    _require_dev_test_auth_secret(x_test_auth_secret)

    if not payload.user_id and not payload.username and not payload.email:
        raise HTTPException(
            status_code=400,
            detail="One of user_id, username, or email is required",
        )

    user = _resolve_test_auth_user(db, payload)
    created = False

    if not user:
        if not payload.create_if_missing:
            raise HTTPException(status_code=404, detail="User not found")
        user = _create_test_auth_user(db, payload)
        created = True

    token = f"dev-token-{user['id']}"
    return DevTestAuthLoginResponse(
        access_token=token,
        user={
            "id": user.get("id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role", "user"),
        },
        created=created,
    )
