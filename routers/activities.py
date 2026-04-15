"""
User activity tracking routes.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from models.activities import UserActivityCreate, UserActivityResponse
from services.auth import get_current_user
from services.database import get_db

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.post("", response_model=UserActivityResponse, status_code=201)
async def log_user_activity(
    activity: UserActivityCreate,
    db=Depends(get_db),
):
    """Log a user activity event"""
    activity_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    activity_data = {
        "id": activity_id,
        "user_id": activity.user_id,
        "type": activity.type,
        "product_id": activity.product_id,
        # DB column is bigint milliseconds since epoch
        "timestamp": int(activity.timestamp),
        "activity_metadata": activity.metadata,  # Use activity_metadata column name
        "created_at": now.isoformat(),
    }

    response = db.table("user_activities").insert(activity_data).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log activity")

    # Map activity_metadata back to metadata for the response
    result = response.data[0]
    if "activity_metadata" in result:
        result["metadata"] = result.pop("activity_metadata")

    # Convert timestamp back to milliseconds for response
    if "timestamp" in result and isinstance(result["timestamp"], str):
        timestamp_str = result["timestamp"]
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        result["timestamp"] = int(dt.timestamp() * 1000)

    return result


@router.get("", response_model=list[UserActivityResponse])
async def get_activities(
    user_id: str | None = None,
    activity_type: str | None = Query(None, alias="type"),
    product_id: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """Get activities with optional filters"""
    query = db.table("user_activities").select("*")

    if user_id:
        query = query.eq("user_id", user_id)

    if activity_type:
        query = query.eq("type", activity_type)

    if product_id:
        query = query.eq("product_id", product_id)

    query = query.range(offset, offset + limit - 1).order("timestamp", desc=True)

    response = query.execute()

    # Map activity_metadata back to metadata for all activities
    activities = response.data or []
    for activity in activities:
        if "activity_metadata" in activity:
            activity["metadata"] = activity.pop("activity_metadata")

        # Convert timestamp back to milliseconds for response
        if "timestamp" in activity and isinstance(activity["timestamp"], str):
            timestamp_str = activity["timestamp"]
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            activity["timestamp"] = int(dt.timestamp() * 1000)

    return activities


@router.get("/{activity_id}", response_model=UserActivityResponse)
async def get_activity(
    activity_id: str,
    db=Depends(get_db),
):
    """Get a specific activity by ID"""
    response = db.table("user_activities").select("*").eq("id", activity_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = response.data[0]
    if "activity_metadata" in activity:
        activity["metadata"] = activity.pop("activity_metadata")
    if "timestamp" in activity and isinstance(activity["timestamp"], str):
        timestamp_str = activity["timestamp"]
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        activity["timestamp"] = int(dt.timestamp() * 1000)

    return activity


@router.post("/cleanup", response_model=dict)
async def cleanup_old_activities(
    days_to_keep: int = 90,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Clean up activities older than specified days (admin only)"""
    # This is an admin-only maintenance function
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Calculate cutoff timestamp (milliseconds)
    import time

    cutoff_ms = int((time.time() - (days_to_keep * 86400)) * 1000)

    # Delete activities older than cutoff
    db.table("user_activities").delete().lt("timestamp", cutoff_ms).execute()

    return {"success": True, "message": f"Cleaned up activities older than {days_to_keep} days"}
