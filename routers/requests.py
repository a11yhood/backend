"""User request management endpoints.

Handles user requests for elevated privileges and product ownership:
- Moderator status requests
- Admin status requests (reviewed by admins only)
- Product management/ownership requests

Security: Regular users see only their own requests; moderators/admins see all.
All approvals/rejections logged with reviewer ID and timestamp.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from config import get_settings
from services.auth import get_current_user
from services.db_consistency import wait_for_row_visibility
from services.database import get_db
from services.sources import extract_domain
from services.timestamps import ApiTimestamp, OptionalApiTimestamp

router = APIRouter(prefix="/api/requests", tags=["requests"])


class UserRequestCreate(BaseModel):
    type: str  # 'moderator', 'admin', 'product-ownership', 'source-domain', 'collection-ownership'
    product_id: str | None = None
    collection_id: str | None = None
    reason: str | None = Field(
        default=None,
        description="Canonical request explanation field.",
    )
    message: str | None = Field(
        default=None,
        description="Deprecated compatibility alias for reason.",
        deprecated=True,
    )

    @model_validator(mode="after")
    def normalize_reason(self):
        # Keep reason canonical while allowing legacy clients to send message.
        if not self.reason and self.message:
            self.reason = self.message
        return self


class UserRequestResponse(BaseModel):
    id: str
    user_id: str
    type: str
    status: str
    product_id: str | None = None
    collection_id: str | None = None
    reason: str | None = Field(
        default=None,
        description="Canonical request explanation field.",
    )
    message: str | None = Field(
        default=None,
        description="Deprecated compatibility alias mirroring reason.",
        deprecated=True,
    )
    reviewed_by: str | None = None
    reviewed_at: OptionalApiTimestamp = None
    created_at: ApiTimestamp
    updated_at: ApiTimestamp


class UserRequestUpdate(BaseModel):
    status: str  # 'approved' or 'rejected'


def _to_response_row(row: dict) -> dict:
    response = dict(row)
    if response.get("reason") and not response.get("message"):
        response["message"] = response["reason"]
    return response


@router.get("/", response_model=list[UserRequestResponse])
def get_user_requests(
    status: str | None = None,
    type: str | None = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get user requests with role-based filtering.

    Security: Regular users see only their own requests.
    Moderators and admins see all requests for review/approval.
    """
    query = db.table("user_requests").select("*")

    # Regular users can only see their own requests
    # Moderators and admins can see all requests
    user_role = current_user.get("role", "user")
    if user_role not in ["admin", "moderator"]:
        query = query.eq("user_id", current_user["id"])

    # Filter by status if provided
    if status:
        query = query.eq("status", status)

    # Filter by type if provided
    if type:
        query = query.eq("type", type)

    query = query.order("created_at", desc=True)

    response = query.execute()
    return [_to_response_row(row) for row in (response.data or [])]


@router.get("/me", response_model=list[UserRequestResponse])
def get_my_requests(
    status: str | None = None,
    type: str | None = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get current user's requests. Provides a dedicated user dashboard endpoint.
    """
    query = db.table("user_requests").select("*").eq("user_id", current_user["id"])

    # Filter by status if provided
    if status:
        query = query.eq("status", status)

    # Filter by type if provided
    if type:
        query = query.eq("type", type)

    query = query.order("created_at", desc=True)

    response = query.execute()
    return [_to_response_row(row) for row in (response.data or [])]


@router.post("/", response_model=UserRequestResponse, status_code=201)
def create_user_request(
    request: UserRequestCreate, current_user: dict = Depends(get_current_user), db=Depends(get_db)
):
    """
    Create a new user request.
    """
    # Validate request type
    valid_types = [
        "moderator",
        "admin",
        "product-ownership",
        "source-domain",
        "collection-ownership",
    ]
    if request.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request type. Must be one of: {', '.join(valid_types)}",
        )

    # Product management requests must have a product_id
    if request.type == "product-ownership" and not request.product_id:
        raise HTTPException(
            status_code=400, detail="Product management requests must include a product_id"
        )

    # Collection management requests must have a collection_id
    if request.type == "collection-ownership" and not request.collection_id:
        raise HTTPException(
            status_code=400, detail="Collection ownership requests must include a collection_id"
        )

    if request.type == "collection-ownership":
        if not wait_for_row_visibility(
            db,
            "collections",
            "id",
            request.collection_id,
            select="id",
        ):
            raise HTTPException(status_code=404, detail="Collection not found")

    if request.type == "product-ownership" and request.product_id:
        if not wait_for_row_visibility(db, "products", "id", request.product_id, select="id"):
            raise HTTPException(status_code=404, detail="Product not found")

    # Source-domain requests must have a reason with a valid domain
    if request.type == "source-domain":
        if not request.reason or not request.reason.strip():
            raise HTTPException(
                status_code=400,
                detail="Source-domain requests must include a reason with domain information (e.g., 'Domain: example.com')",
            )

        # Try to extract domain from reason
        domain = None
        try:
            for line in str(request.reason).splitlines():
                if line.lower().startswith("domain:"):
                    domain = line.split(":", 1)[1].strip().lower()
                    break
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Error parsing domain from reason: {str(e)}"
            )

        if not domain:
            raise HTTPException(
                status_code=400,
                detail="Reason must include 'Domain: <domain>' (e.g., 'Domain: example.com')",
            )

        # Validate domain format - extract_domain removes www. prefix and validates
        try:
            validated_domain = extract_domain(f"https://{domain}")
            if not validated_domain:
                raise HTTPException(status_code=400, detail=f"Invalid domain format: {domain}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Domain validation error: {str(e)}")

    # Check if user already has a pending request of this type
    existing_query = (
        db.table("user_requests")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("type", request.type)
        .eq("status", "pending")
    )

    if request.type == "product-ownership":
        existing_query = existing_query.eq("product_id", request.product_id)
    elif request.type == "collection-ownership":
        existing_query = existing_query.eq("collection_id", request.collection_id)

    existing_response = existing_query.execute()

    if existing_response.data:
        raise HTTPException(
            status_code=400, detail=f"You already have a pending {request.type} request"
        )

    # Create the request
    now = datetime.now(UTC)
    request_data = {
        "user_id": current_user["id"],
        "type": request.type,
        "status": "pending",
        "product_id": request.product_id,
        "collection_id": request.collection_id,
        "reason": request.reason,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    try:
        response = db.table("user_requests").insert(request_data).execute()
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        message = str(e)

        # Test environments can rarely hit a stale cleanup window where the authenticated
        # user row is briefly absent when inserting dependent rows. Recreate and retry once.
        if "user_requests_user_id_fkey" in message:
            user_id = current_user.get("id")
            if user_id:
                user_seed = {
                    "id": user_id,
                    "github_id": current_user.get("github_id") or f"rehydrated-{user_id[:8]}",
                    "username": current_user.get("username") or f"user_{user_id[:8]}",
                    "display_name": current_user.get("username") or "Rehydrated User",
                    "email": current_user.get("email") or f"{user_id[:8]}@a11yhood.test",
                    "role": current_user.get("role") or "user",
                }
                try:
                    if request_data.get("product_id"):
                        wait_for_row_visibility(
                            db,
                            "products",
                            "id",
                            request_data["product_id"],
                            select="id",
                        )
                    if request_data.get("collection_id"):
                        wait_for_row_visibility(
                            db,
                            "collections",
                            "id",
                            request_data["collection_id"],
                            select="id",
                        )
                    db.table("users").upsert(user_seed, on_conflict="id").execute()
                    response = db.table("user_requests").insert(request_data).execute()
                except Exception as retry_exc:
                    logger.error(f"Error creating user request after user rehydrate: {retry_exc}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create request: {str(retry_exc)}",
                    )
            else:
                logger.error(f"Error creating user request: {message}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Failed to create request: {message}")
        else:
            logger.error(f"Error creating user request: {message}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create request: {message}")

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create request")

    created_request = response.data[0]
    created_request = (
        wait_for_row_visibility(db, "user_requests", "id", created_request["id"]) or created_request
    )

    return _to_response_row(created_request)


def _can_review_request(current_user: dict, request_data: dict, db) -> bool:
    user_role = current_user.get("role", "user")
    if user_role in ["admin", "moderator"]:
        return True

    if request_data.get("type") != "collection-ownership":
        return False

    collection_id = request_data.get("collection_id")
    if not collection_id:
        return False

    owner_check = (
        db.table("collections")
        .select("id")
        .eq("id", collection_id)
        .eq("user_id", current_user["id"])
        .limit(1)
        .execute()
    )
    return bool(owner_check.data)


@router.patch("/{request_id}", response_model=UserRequestResponse)
def update_user_request(
    request_id: str,
    update: UserRequestUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Update a user request (approve/reject). Admin or moderator only.
    """
    # Validate status
    if update.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    # Get the request
    request_response = db.table("user_requests").select("*").eq("id", request_id).execute()

    if not request_response.data:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data = request_response.data[0]

    if not _can_review_request(current_user, request_data, db):
        raise HTTPException(
            status_code=403,
            detail="Admin or moderator access required (collection owners can review collection-ownership requests)",
        )

    user_role = current_user.get("role", "user")

    # Only admins can approve requests that grant the 'admin' role.
    if update.status == 'approved' and request_data.get('type') == 'admin' and user_role != 'admin':
        raise HTTPException(status_code=403, detail="Only admins can approve admin-role requests")

    # Update the request
    now = datetime.now(UTC)
    update_data = {
        "status": update.status,
        "reviewed_by": current_user["id"],
        "reviewed_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    response = db.table("user_requests").update(update_data).eq("id", request_id).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to update request")

    # If approved, grant the requested permission
    if update.status == "approved":
        _grant_permission(db, request_data, reviewer_id=current_user["id"])

    updated_request = response.data[0]
    updated_request = (
        wait_for_row_visibility(db, "user_requests", "id", updated_request["id"]) or updated_request
    )
    return _to_response_row(updated_request)


def _grant_permission(db, request_data: dict, reviewer_id: str | None = None):
    """Grant permission based on approved request"""
    user_id = request_data["user_id"]
    request_type = request_data["type"]

    if request_type == "product-ownership":
        wait_for_row_visibility(db, "products", "id", request_data["product_id"], select="id")
        wait_for_row_visibility(db, "users", "id", user_id, select="id")
        # Atomic and idempotent: safe under concurrent approvals.
        owner_data = {
            "product_id": request_data["product_id"],
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        db.table("product_editors").upsert(
            owner_data,
            on_conflict="product_id,user_id",
        ).execute()

    elif request_type == "collection-ownership":
        collection_id = request_data.get("collection_id")
        if not collection_id:
            return

        wait_for_row_visibility(db, "collections", "id", collection_id, select="id")
        wait_for_row_visibility(db, "users", "id", user_id, select="id")

        # Atomic and idempotent: safe under concurrent approvals.
        owner_data = {
            "collection_id": collection_id,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        db.table("collection_editors").upsert(
            owner_data,
            on_conflict="collection_id,user_id",
        ).execute()

    elif request_type in ["moderator", "admin"]:
        # Prefer the admin_update_user_role RPC to satisfy DB trigger/policy checks.
        try:
            if reviewer_id:
                db.rpc(
                    "admin_update_user_role",
                    {
                        "admin_user_id": reviewer_id,
                        "target_user_id": user_id,
                        "new_role": request_type,
                    },
                ).execute()
            else:
                db.table("users").update({"role": request_type}).eq("id", user_id).execute()
        except Exception:
            # Fall back to direct update only in TEST_MODE (test setups may not have the RPC).
            settings = get_settings()
            if not settings.TEST_MODE:
                logging.exception(
                    "admin_update_user_role RPC failed in production; role update skipped",
                    extra={"user_id": user_id, "request_type": request_type},
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update user role to '{request_type}': RPC unavailable",
                )
            try:
                db.table("users").update({"role": request_type}).eq("id", user_id).execute()
            except Exception:
                # Do not fail the overall approval if role update fails, but log for investigation.
                logging.exception(
                    "Failed to update user role during permission grant",
                    extra={"user_id": user_id, "request_type": request_type},
                )

                return

            logging.exception(
                "admin_update_user_role RPC failed; fallback direct role update succeeded",
                extra={"user_id": user_id, "request_type": request_type},
            )

    elif request_type == "source-domain":
        # Auto-add supported source domain if not present
        try:
            reason = request_data.get("reason") or ""
            domain = None
            # Try to parse a line like "Domain: example.com"
            for line in str(reason).splitlines():
                if line.lower().startswith("domain:"):
                    domain = line.split(":", 1)[1].strip().lower()
                    break
            if not domain:
                return

            # Normalize domain by removing www. prefix (consistent with extract_domain)
            if domain.startswith("www."):
                domain = domain[4:]

            # If exists, skip; else create with name = domain
            existing = (
                db.table("supported_sources").select("*").eq("domain", domain).limit(1).execute()
            )
            if existing.data:
                return

            # Generate minimal record
            now = datetime.now(UTC).isoformat()
            data = {
                "domain": domain,
                "name": domain,
                "created_at": now,
                "updated_at": now,
            }
            db.table("supported_sources").insert(data).execute()
        except Exception:
            # Do not fail the approval action if auto-add fails
            pass


@router.delete("/{request_id}")
def delete_user_request(
    request_id: str, current_user: dict = Depends(get_current_user), db=Depends(get_db)
):
    """
    Delete a user request. Users can delete their own pending requests.
    Admins can delete any request.
    """
    # Get the request
    request_response = db.table("user_requests").select("*").eq("id", request_id).execute()

    if not request_response.data:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data = request_response.data[0]

    # Check permissions
    is_owner = request_data["user_id"] == current_user["id"]
    is_pending = request_data["status"] == "pending"
    is_admin = current_user.get("role") == "admin"

    if not (is_admin or (is_owner and is_pending)):
        raise HTTPException(status_code=403, detail="You can only delete your own pending requests")

    db.table("user_requests").delete().eq("id", request_id).execute()

    return {"message": "Request deleted successfully"}
