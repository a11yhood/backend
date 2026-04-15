"""Rating management endpoints.

Handles product ratings (1-5 stars).
Security: One rating per user per product (enforced at creation).
Users can only update/delete their own ratings.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from models.ratings import RatingCreate, RatingResponse, RatingUpdate
from services.auth import get_current_user
from services.database import get_db

router = APIRouter(prefix="/api/ratings", tags=["ratings"])


@router.get("", response_model=list[RatingResponse])
async def get_ratings(
    product_id: str | None = None,
    user_id: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """Get ratings with optional filters"""
    query = db.table("ratings").select("*")

    if product_id:
        query = query.eq("product_id", product_id)

    if user_id:
        query = query.eq("user_id", user_id)

    query = query.range(offset, offset + limit - 1).order("created_at", desc=True)

    response = query.execute()
    return response.data


@router.get("/{rating_id}", response_model=RatingResponse)
async def get_rating(
    rating_id: str,
    db=Depends(get_db),
):
    """Get a single rating by ID"""
    response = db.table("ratings").select("*").eq("id", rating_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Rating not found")

    return response.data[0]


@router.post("", response_model=RatingResponse, status_code=201)
async def create_rating(
    rating: RatingCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new rating (authenticated users only).

    Security: Prevents duplicate ratings by checking user_id + product_id uniqueness.
    If user already rated this product, returns 400 error.
    """
    # Check if user already rated this product
    existing = (
        db.table("ratings")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("product_id", rating.product_id)
        .execute()
    )

    if existing.data:
        raise HTTPException(status_code=400, detail="You have already rated this product")

    rating_data = rating.model_dump()
    rating_data["user_id"] = current_user["id"]

    response = db.table("ratings").insert(rating_data).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create rating")

    return response.data[0]


@router.put("/{rating_id}", response_model=RatingResponse)
async def update_rating(
    rating_id: str,
    rating: RatingUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update a rating (owner only).

    Security: Enforces ownership check; users can only modify their own ratings.
    Prevents IDOR attacks by validating user_id matches current_user.
    """
    # Check if rating exists and user owns it
    existing = db.table("ratings").select("*").eq("id", rating_id).execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Rating not found")

    if existing.data[0]["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to update this rating")

    update_data = rating.model_dump(exclude_unset=True)
    response = db.table("ratings").update(update_data).eq("id", rating_id).execute()

    return response.data[0]


@router.delete("/{rating_id}", status_code=204)
async def delete_rating(
    rating_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a rating (owner or admin only)"""
    existing = db.table("ratings").select("*").eq("id", rating_id).execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Rating not found")

    if (
        existing.data[0]["user_id"] != current_user["id"]
        and not current_user.get("role") == "admin"
    ):
        raise HTTPException(status_code=403, detail="Not authorized to delete this rating")

    db.table("ratings").delete().eq("id", rating_id).execute()
    return None


@router.put("/{product_id}/{user_id}", response_model=RatingResponse)
async def upsert_rating_by_product_user(
    product_id: str,
    user_id: str,
    rating: RatingUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create or update a rating for a specific product and user"""
    # Verify user is updating their own rating (unless admin)
    if current_user["id"] != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this rating")

    # Check if rating exists
    existing = (
        db.table("ratings")
        .select("*")
        .eq("product_id", product_id)
        .eq("user_id", user_id)
        .execute()
    )

    if existing.data:
        # Update existing rating
        update_data = rating.model_dump(exclude_unset=True)
        response = (
            db.table("ratings").update(update_data).eq("id", existing.data[0]["id"]).execute()
        )
        return response.data[0]
    else:
        # Create new rating
        rating_data = rating.model_dump(exclude_unset=True)
        rating_data["product_id"] = product_id
        rating_data["user_id"] = user_id
        response = db.table("ratings").insert(rating_data).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create rating")

        return response.data[0]
