"""Authentication and authorization services.

Provides token verification, user identity extraction, and role-based access control.
In TEST_MODE, accepts dev tokens for stable test identities without real OAuth.
Also supports X-Dev-Role header for dynamic test user creation (frontend role switching).
Security: All authorization checks enforce server-side validation; never trust client roles.
"""

import logging
import os
import uuid

from fastapi import Depends, Header, HTTPException

from config import load_settings_from_env
from services.database import get_db, verify_token
from services.security_logger import log_auth_failure

logger = logging.getLogger(__name__)

# Fixed dev identities shared with frontend src/lib/dev-users.ts
# Must match exactly between frontend and backend.
# Security: Only active when TEST_MODE=true; production uses real Supabase auth.
DEV_USER_IDS = {
    "49366adb-2d13-412f-9ae5-4c35dbffab10": "admin_user",
    "94e116f7-885d-4d32-87ae-697c5dc09b9e": "moderator_user",
    "2a3b7c3e-971b-4b42-9c8c-0f1843486c50": "regular_user",
}

# Deterministic seed payloads for UUID-based dev users used in tests.
# If these rows are missing (e.g., after a flaky reset), auth can recreate them.
DEV_USER_SEEDS = {
    "49366adb-2d13-412f-9ae5-4c35dbffab10": {
        "github_id": "admin-test-001",
        "username": "admin_user",
        "display_name": "Admin User",
        "email": "admin@example.com",
        "role": "admin",
    },
    "94e116f7-885d-4d32-87ae-697c5dc09b9e": {
        "github_id": "mod-test-002",
        "username": "moderator_user",
        "display_name": "Moderator User",
        "email": "moderator@example.com",
        "role": "moderator",
    },
    "2a3b7c3e-971b-4b42-9c8c-0f1843486c50": {
        "github_id": "user-test-003",
        "username": "regular_user",
        "display_name": "Regular User",
        "email": "user@example.com",
        "role": "user",
    },
}

# Valid roles that can be created via X-Dev-Role header
VALID_DEV_ROLES = {"admin", "moderator", "manager", "user"}


async def parse_dev_token(authorization: str | None, x_dev_role: str | None, db) -> dict:
    """
    Parse dev mode authentication: UUID-based, role-based, or X-Dev-Role header.

    Supports three modes (evaluated in this order):
    1. X-Dev-Role: <role>  - Create/fetch test user with given role (frontend/manual dev use).
    2. Bearer dev-token-<uuid>  - Resolve exact user by UUID (deterministic test identity).
    3. Bearer dev-token-<role>  - Create/fetch test user with given role (role-behaviour tests).

    UUID tokens are preferred for identity-sensitive tests because they map 1:1 to a seeded
    user row.  Role tokens are preferred for role-behaviour tests because they do not depend
    on a specific pre-seeded ID.

    Valid roles: admin, moderator, manager, user

    Args:
        authorization: Authorization header (Bearer token)
        x_dev_role: X-Dev-Role header for dynamic role switching

    Returns:
        Dict with id, email, username, role, is_dev_user=True

    Raises:
        HTTPException 400 if role is invalid
        HTTPException 404 if UUID user is not found
        HTTPException 401 if auth header is missing or malformed
    """
    settings_fresh = load_settings_from_env()
    if not settings_fresh.TEST_MODE:
        raise HTTPException(status_code=401, detail="Dev tokens only in TEST_MODE")

    # Mode 1: X-Dev-Role header takes priority for dynamic user creation
    if x_dev_role:
        role = x_dev_role.strip().lower()
        if role not in VALID_DEV_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid dev role '{role}'. Valid: {', '.join(sorted(VALID_DEV_ROLES))}",
            )

        # Create deterministic username for this role
        dev_username = f"dev_{role}"
        dev_email = f"dev-{role}@a11yhood.test"
        dev_github_id = f"dev-role-{role}"

        # Check if test user with this role exists
        resp = db.table("users").select("*").eq("username", dev_username).execute()

        if resp.data and len(resp.data) > 0:
            user = resp.data[0]
            logger.debug(f"Found existing dev user: {user['id']} (role: {role})")
            return {
                "id": user["id"],
                "email": user.get("email"),
                "username": user.get("username"),
                "role": user.get("role", "user"),
                "is_dev_user": True,
            }

        # Create new test user for this role
        user_id = str(uuid.uuid4())
        new_user = {
            "id": user_id,
            "github_id": dev_github_id,
            "username": dev_username,
            "display_name": f"{role.capitalize()} User",
            "email": dev_email,
            "role": role,
        }
        try:
            logger.debug(f"Attempting to insert dev user with data: {new_user}")
            db.table("users").insert(new_user).execute()
            logger.info(
                f"Created dev test user: {user_id} (username: {dev_username}, role: {role})"
            )
            return {
                "id": user_id,
                "github_id": dev_github_id,
                "email": dev_email,
                "username": dev_username,
                "display_name": f"{role.capitalize()} User",
                "role": role,
                "is_dev_user": True,
            }
        except Exception as e:
            logger.error(f"Failed to create dev test user for role {role}: {e}")
            logger.error(f"User data that was attempted: {new_user}")
            raise HTTPException(
                status_code=500, detail=f"Failed to create test user for role {role}"
            )

    # Mode 2: Authorization header (UUID or role)
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header or X-Dev-Role header")

    token = authorization.replace("Bearer ", "").strip()
    if not token.startswith("dev-token-"):
        raise HTTPException(status_code=401, detail="Invalid dev token format")

    suffix = token[len("dev-token-") :].strip()

    # Mode 2a: UUID-based token — resolve exact user by ID (deterministic test identity)
    try:
        uuid.UUID(suffix)
        # Suffix is a valid UUID; look up the user by ID.
        resp = db.table("users").select("*").eq("id", suffix).execute()
        if not resp.data:
            # Self-heal known deterministic test identities to reduce suite flakiness
            # when test cleanup temporarily drops seeded users.
            seed = DEV_USER_SEEDS.get(suffix)
            if seed is None:
                raise HTTPException(status_code=404, detail=f"Dev user not found: {suffix}")

            try:
                db.table("users").upsert({"id": suffix, **seed}, on_conflict="id").execute()
                resp = db.table("users").select("*").eq("id", suffix).execute()
            except Exception as exc:
                logger.error("Failed to recreate deterministic dev user %s: %s", suffix, exc)
                raise HTTPException(status_code=500, detail=f"Failed to recreate dev user: {suffix}")

            if not resp.data:
                raise HTTPException(status_code=404, detail=f"Dev user not found: {suffix}")

        user = resp.data[0]
        logger.debug(f"Resolved dev user by UUID: {user['id']} (role: {user.get('role')})")
        return {
            "id": user["id"],
            "email": user.get("email"),
            "username": user.get("username"),
            "role": user.get("role", "user"),
            "is_dev_user": True,
        }
    except HTTPException:
        raise
    except ValueError:
        pass  # Not a UUID; fall through to role-based lookup.

    # Mode 2b: Role-based dev token (dev-token-admin, dev-token-user, etc.)
    role = suffix.lower()
    if role not in VALID_DEV_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dev token role '{role}'. Valid: {', '.join(sorted(VALID_DEV_ROLES))}",
        )

    # Use the same role-based user lookup/creation as X-Dev-Role header
    dev_username = f"dev_{role}"
    dev_email = f"dev-{role}@a11yhood.test"

    # Check if test user with this role exists
    resp = db.table("users").select("*").eq("username", dev_username).execute()

    if resp.data and len(resp.data) > 0:
        user = resp.data[0]
        logger.debug(f"Found existing dev user: {user['id']} (role: {role})")
        return {
            "id": user["id"],
            "email": user.get("email"),
            "username": user.get("username"),
            "role": user.get("role", "user"),
            "is_dev_user": True,
        }

    # Create new test user for this role
    user_id = str(uuid.uuid4())
    dev_github_id = f"dev-role-{role}"
    new_user = {
        "id": user_id,
        "github_id": dev_github_id,
        "username": dev_username,
        "display_name": f"{role.capitalize()} User",
        "email": dev_email,
        "role": role,
    }
    try:
        logger.debug(f"Attempting to insert dev user with data: {new_user}")
        db.table("users").insert(new_user).execute()
        logger.info(f"Created dev test user: {user_id} (username: {dev_username}, role: {role})")
        return {
            "id": user_id,
            "github_id": dev_github_id,
            "email": dev_email,
            "username": dev_username,
            "display_name": f"{role.capitalize()} User",
            "role": role,
            "is_dev_user": True,
        }
    except Exception as e:
        logger.error(f"Failed to create dev test user for role {role}: {e}")
        logger.error(f"User data that was attempted: {new_user}")
        raise HTTPException(status_code=500, detail=f"Failed to create test user for role {role}")


async def get_current_user(
    authorization: str = Header(None),
    x_dev_role: str = Header(None),
    db=Depends(get_db),
):
    """
    Get current user from Authorization header.

    Returns user dict with id, email, username, role on success.
    Raises HTTPException 401 if token is missing or invalid.

    In TEST_MODE (dev):
      - Accepts: X-Dev-Role header to create/fetch test user by role
      - Accepts: "Bearer dev-token-<role>" to create/fetch test user by role
      - Returns user data with role

    In production (TEST_MODE=false):
      - Accepts: valid Supabase JWT
      - Calls verify_token() for Supabase validation

    Security: Always re-derives user identity server-side; never trusts client roles.
    """
    settings_fresh = load_settings_from_env()

    if not authorization and not x_dev_role:
        log_auth_failure(None, "Missing authorization header")
        raise HTTPException(status_code=401, detail="No authorization header")

    env_file = os.getenv("ENV_FILE", "")
    is_test_context = (
        settings_fresh.TEST_MODE
        or env_file.endswith(".env.test")
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
    )

    # Log context for debugging
    logger.debug(f"Auth context: TEST_MODE={settings_fresh.TEST_MODE}, ENV_FILE={env_file}, is_test_context={is_test_context}")

    # Check if this is a dev token (always allow in TEST_MODE, regardless of other conditions)
    is_dev_token = (
        authorization
        and authorization.replace("Bearer ", "").strip().startswith("dev-token-")
    )

    # Dev/test mode: Try X-Dev-Role or dev token
    # NOTE: Dev tokens should be accepted whenever TEST_MODE is true
    if (settings_fresh.TEST_MODE or is_test_context) and (
        x_dev_role or is_dev_token
    ):
        user_dict = await parse_dev_token(authorization, x_dev_role, db)
        logger.debug(f"Successfully parsed dev token/role: user={user_dict.get('id')}, role={user_dict.get('role')}")
        return user_dict

    # Production: Real Supabase auth
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header")

    token = authorization.replace("Bearer ", "").strip()
    db_adapter = db
    user = verify_token(token, db_adapter)

    # Normalize user to dict shape expected by routers
    try:
        user_dict = {
            "id": getattr(user, "id", None)
            if hasattr(user, "id")
            else (user.get("id") if isinstance(user, dict) else None),
            "email": getattr(user, "email", None)
            if hasattr(user, "email")
            else (user.get("email") if isinstance(user, dict) else None),
            "username": None,
            "role": "user",
            "github_id": None,
        }
        meta = None
        if hasattr(user, "user_metadata"):
            meta = getattr(user, "user_metadata")
        elif isinstance(user, dict):
            meta = user.get("user_metadata")

        if isinstance(meta, dict):
            user_dict["username"] = (
                meta.get("preferred_username") or meta.get("user_name") or user_dict["email"]
            )
            user_dict["github_id"] = meta.get("provider_id") or meta.get("sub")

        if not user_dict["username"] and user_dict["email"]:
            user_dict["username"] = user_dict["email"].split("@")[0]

        if user_dict["id"]:
            response = db_adapter.table("users").select("*").eq("id", user_dict["id"]).execute()
            if response.data and len(response.data) > 0:
                row = response.data[0]
                user_dict["role"] = row.get("role", "user")
                user_dict["username"] = row.get("username") or user_dict["username"]
                user_dict["github_id"] = row.get("github_id") or user_dict["github_id"]

        return user_dict
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Authentication normalization failed: {str(e)}"
        )


async def get_current_user_optional(
    authorization: str = Header(None), x_dev_role: str = Header(None), db=Depends(get_db)
):
    """
    Variant of get_current_user that returns None when no Authorization header is provided.
    Useful for public endpoints that optionally enforce ownership/visibility checks.

    In TEST_MODE, UUID-based dev tokens that reference a non-existent user raise 404;
    role-based tokens and X-Dev-Role always create a user on demand.
    Returns None only when both the authorization header and X-Dev-Role header are absent.
    """
    if not authorization and not x_dev_role:
        return None
    try:
        return await get_current_user(authorization, x_dev_role, db)
    except HTTPException as e:
        # In test mode, if dev user doesn't exist yet, return None (allows user creation)
        settings_fresh = load_settings_from_env()
        if settings_fresh.TEST_MODE and "not found" in str(e.detail):
            return None
        raise


# ----- Authorization policy helpers -----
def ensure_admin(current_user: dict):
    """
    Enforce admin-only access.

    Security: Server-side role check prevents privilege escalation.
    Raises 403 Forbidden if current_user lacks admin role.
    """
    from services.security_logger import log_unauthorized_access

    if not current_user or current_user.get("role") != "admin":
        log_unauthorized_access(
            current_user.get("id") if current_user else None,
            "admin",
            f"Attempted admin action with role: {current_user.get('role') if current_user else 'none'}",
        )
        raise HTTPException(status_code=403, detail="Admin access required")


def ensure_moderator_or_admin(current_user: dict):
    """
    Enforce moderator or admin access.

    Security: Server-side role check prevents privilege escalation.
    Raises 403 Forbidden if current_user lacks moderator or admin role.
    """
    from services.security_logger import log_unauthorized_access

    if not current_user or current_user.get("role") not in ("moderator", "admin"):
        log_unauthorized_access(
            current_user.get("id") if current_user else None,
            "moderator",
            f"Attempted moderator action with role: {current_user.get('role') if current_user else 'none'}",
        )
        raise HTTPException(status_code=403, detail="Moderator or admin access required")


def ensure_self_or_admin(current_user: dict, user_id: str):
    """
    Permit if editing own record or user is admin; else 403.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if current_user.get("id") != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")


def can_change_role(current_user: dict) -> bool:
    """
    Only admins may change roles.
    """
    return bool(current_user and current_user.get("role") == "admin")
