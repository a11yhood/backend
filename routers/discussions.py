"""Discussion/comment management endpoints.

Supports threaded discussions via parent_id for reply chains.
Security: Users can only edit/delete their own comments.
All discussion content should be sanitized before rendering to prevent XSS.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional
from supabase import Client
from datetime import datetime, timezone
from uuid import UUID

from models.discussions import DiscussionCreate, DiscussionUpdate, DiscussionResponse, DiscussionBlockRequest
from services.database import get_db
from services.auth import get_current_user
from services.sanitizer import sanitize_html

router = APIRouter(prefix="/api/discussions", tags=["discussions"])


@router.get("", response_model=list[DiscussionResponse])
async def get_discussions(
    product_id: Optional[str] = None,
    user_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    response: Response = None,
    db = Depends(get_db),
):
    """Get discussions with optional filters"""
    query = db.table("discussions").select("*")
    
    if product_id:
        query = query.eq("product_id", product_id)
    
    if user_id:
        query = query.eq("user_id", user_id)
    
    if parent_id:
        query = query.eq("parent_id", parent_id)
    
    query = query.range(offset, offset + limit - 1).order("created_at", desc=True)
    
    db_resp = query.execute()
    # Cache for 1 minute to reduce load
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
    return db_resp.data


@router.get("/{discussion_id}", response_model=DiscussionResponse)
async def get_discussion(
    discussion_id: UUID,
    db = Depends(get_db),
):
    """Get a single discussion by ID"""
    response = db.table("discussions").select("*").eq("id", str(discussion_id)).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Discussion not found")
    
    return response.data[0]


@router.post("", response_model=DiscussionResponse, status_code=201)
async def create_discussion(
    discussion: DiscussionCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Create a new discussion comment (authenticated users only).
    
    Automatically populates username field from users table for display.
    This denormalization avoids joins when fetching discussion threads.
    """
    discussion_data = discussion.model_dump()
    discussion_data["user_id"] = current_user["id"]
    # Use authenticated user's username directly (denormalize for display)
    discussion_data["username"] = current_user.get("username")
    
    # Sanitize user-generated content to prevent XSS
    discussion_data["content"] = sanitize_html(discussion_data.get("content", ""))
    
    response = db.table("discussions").insert(discussion_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create discussion")
    
    # The insert returns the data including the username we just inserted
    created_discussion = response.data[0]
    
    # Ensure username is in the response (it should be from the insert)
    if "username" not in created_discussion:
        created_discussion["username"] = discussion_data["username"]
    
    return created_discussion


@router.put("/{discussion_id}", response_model=DiscussionResponse)
async def update_discussion(
    discussion_id: UUID,
    discussion: DiscussionUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Update a discussion (owner only)"""
    existing = db.table("discussions").select("*").eq("id", str(discussion_id)).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Discussion not found")
    
    if existing.data[0]["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this discussion")
    
    update_data = discussion.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    # Sanitize content if being updated
    if "content" in update_data:
        update_data["content"] = sanitize_html(update_data["content"])
    
    response = db.table("discussions").update(update_data).eq("id", str(discussion_id)).execute()
    
    return response.data[0]


@router.delete("/{discussion_id}", response_model=DiscussionResponse)
async def delete_discussion(
    discussion_id: UUID,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Soft-delete a discussion (owner or admin only).
    The record remains so replies stay intact; content is replaced with "[deleted]".
    """
    existing = db.table("discussions").select("*").eq("id", str(discussion_id)).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Discussion not found")
    
    if existing.data[0]["user_id"] != current_user["id"] and current_user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this discussion")
    
    response = db.table("discussions").update({
        "content": "[deleted]",
        "updated_at": datetime.now(timezone.utc),
    }).eq("id", str(discussion_id)).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to delete discussion")
    return response.data[0]


@router.post("/{discussion_id}/block", response_model=DiscussionResponse)
async def block_discussion(
    discussion_id: UUID,
    payload: DiscussionBlockRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Block a discussion (admin or moderator only)."""
    if current_user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Not authorized to block discussions")

    existing = db.table("discussions").select("*").eq("id", str(discussion_id)).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Discussion not found")

    now = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    response = db.table("discussions").update({
        "blocked": True,
        "blocked_by": current_user["id"],
        "blocked_reason": payload.reason,
        "blocked_at": now,
        "updated_at": now,
    }).eq("id", str(discussion_id)).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to block discussion")

    # Cascade block to all descendant replies
    to_visit = [str(discussion_id)]
    visited = set()
    while to_visit:
        # Fetch direct children of any node in to_visit
        children_resp = db.table("discussions").select("id").in_("parent_id", to_visit).execute()
        child_ids = [row["id"] for row in (children_resp.data or []) if row.get("id")]
        if not child_ids:
            break
        # Update children to blocked
        db.table("discussions").update({
            "blocked": True,
            "blocked_by": current_user["id"],
            "blocked_reason": payload.reason,
            "blocked_at": now,
            "updated_at": now,
        }).in_("id", child_ids).execute()
        # Continue BFS
        visited.update(child_ids)
        to_visit = child_ids

    return response.data[0]


@router.post("/{discussion_id}/unblock", response_model=DiscussionResponse)
async def unblock_discussion(
    discussion_id: UUID,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Unblock a discussion (admin or moderator only)."""
    if current_user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Not authorized to unblock discussions")

    existing = db.table("discussions").select("*").eq("id", str(discussion_id)).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Discussion not found")

    response = db.table("discussions").update({
        "blocked": False,
        "blocked_by": None,
        "blocked_reason": None,
        "blocked_at": None,
        "updated_at": datetime.now(timezone.utc),
    }).eq("id", str(discussion_id)).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to unblock discussion")

    # Cascade unblock to all descendant replies
    to_visit = [str(discussion_id)]
    while to_visit:
        children_resp = db.table("discussions").select("id").in_("parent_id", to_visit).execute()
        child_ids = [row["id"] for row in (children_resp.data or []) if row.get("id")]
        if not child_ids:
            break
        db.table("discussions").update({
            "blocked": False,
            "blocked_by": None,
            "blocked_reason": None,
            "blocked_at": None,
            "updated_at": datetime.now(timezone.utc),
        }).in_("id", child_ids).execute()
        to_visit = child_ids

    return response.data[0]
