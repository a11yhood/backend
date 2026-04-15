from fastapi import APIRouter, Depends, HTTPException

from models.product_urls import ProductUrlCreate, ProductUrlResponse, ProductUrlUpdate
from services.auth import get_current_user
from services.database import get_db

router = APIRouter(prefix="/api/products", tags=["product-urls"])


@router.post("/{product_id}/urls", response_model=ProductUrlResponse, status_code=201)
async def add_product_url(
    product_id: str,
    url_data: ProductUrlCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Add a new URL to a product. User must be product manager."""
    # Check product exists
    product_response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product = product_response.data[0]
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user

    # Get actual editors from product_editors table
    owners_response = (
        db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
    )
    editor_ids = (
        [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
    )

    # Check authorization
    if user_id not in editor_ids and product.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="Only product manager can add URLs")

    # Add URL
    url_record = {
        "product_id": product_id,
        "url": str(url_data.url),
        "description": url_data.description,
        "created_by": user_id,
    }

    result = db.table("product_urls").insert(url_record).execute()

    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to add URL")

    return result.data[0]


@router.get("/{product_id}/urls", response_model=list[ProductUrlResponse])
async def get_product_urls(
    product_id: str,
    db=Depends(get_db),
):
    """Get all URLs for a product."""
    # Check product exists
    product_response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")

    result = (
        db.table("product_urls")
        .select("*")
        .eq("product_id", product_id)
        .order("created_at")
        .execute()
    )

    return result.data


@router.patch("/{product_id}/urls/{url_id}", response_model=ProductUrlResponse)
async def update_product_url(
    product_id: str,
    url_id: str,
    url_data: ProductUrlUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update a product URL. User must be the one who created it or product manager."""
    # Check URL exists
    url_response = (
        db.table("product_urls")
        .select("*")
        .eq("id", url_id)
        .eq("product_id", product_id)
        .limit(1)
        .execute()
    )
    if not url_response.data:
        raise HTTPException(status_code=404, detail="URL not found")

    url_record = url_response.data[0]
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user

    # Check authorization
    if url_record["created_by"] != user_id:
        product_response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
        if product_response.data:
            product = product_response.data[0]
            owners_response = (
                db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
            )
            editor_ids = (
                [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
            )
            if user_id not in editor_ids and product.get("created_by") != user_id:
                raise HTTPException(status_code=403, detail="Not authorized to update this URL")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to update this URL")

    # Update
    update_data = url_data.model_dump(exclude_unset=True)
    if "url" in update_data:
        update_data["url"] = str(update_data["url"])

    result = db.table("product_urls").update(update_data).eq("id", url_id).execute()

    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update URL")

    return result.data[0]


@router.delete("/{product_id}/urls/{url_id}", status_code=204)
async def delete_product_url(
    product_id: str,
    url_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a product URL. User must be product manager."""
    # Check URL exists
    url_response = (
        db.table("product_urls")
        .select("*")
        .eq("id", url_id)
        .eq("product_id", product_id)
        .limit(1)
        .execute()
    )
    if not url_response.data:
        raise HTTPException(status_code=404, detail="URL not found")

    # Check authorization
    product_response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product = product_response.data[0]
    # Get editor_ids from product_editors table
    editors_response = (
        db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
    )
    editor_ids = (
        [editor["user_id"] for editor in editors_response.data] if editors_response.data else []
    )
    user_id = current_user.get("id") if isinstance(current_user, dict) else current_user

    if user_id not in editor_ids and product.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="Only product manager can delete URLs")

    db.table("product_urls").delete().eq("id", url_id).execute()

    return None
