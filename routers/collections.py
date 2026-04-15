"""Collection management endpoints.

Supports user-curated product collections with public/private visibility.
All mutations require authentication and enforce ownership checks.
Security: Users can only modify their own collections unless admin.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from models.collections import (
    CollectionCreate,
    CollectionFromSearchCreate,
    CollectionResponse,
    CollectionUpdate,
    ProductIdsRequest,
)
from services.auth import get_current_user, get_current_user_optional
from services.database import get_db
from services.id_generator import generate_id_with_uniqueness_check

router = APIRouter(prefix="/api/collections", tags=["collections"])
logger = logging.getLogger(__name__)


def _looks_like_uuid(value: str) -> bool:
    """Check if a string looks like a UUID."""
    try:
        uuid.UUID(str(value))
        return True
    except Exception as e:
        logger.error(f"uuid error: {type(e).__name__}: {str(e)}")
        return False


@router.post("", response_model=CollectionResponse, status_code=201)
async def create_collection(
    collection_data: CollectionCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new collection for the authenticated user.

    Generates human-readable ID from collection name (e.g., "my-collection").
    Security: Requires authentication; collection automatically associated with creator.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")
    user_name = current_user.get("username", "Unknown")

    # Validate input
    if not collection_data.name or not collection_data.name.strip():
        raise HTTPException(status_code=400, detail="Collection name is required")

    if collection_data.description and len(collection_data.description) > 1000:
        raise HTTPException(status_code=400, detail="Description must be 1000 characters or less")

    # Generate UUID primary key and slug
    slug = generate_id_with_uniqueness_check(collection_data.name, db, "collections", column="slug")

    collection = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "user_id": user_id,
        "user_name": user_name,
        "name": collection_data.name,
        "description": collection_data.description,
        "is_public": collection_data.is_public,
    }

    # Insert into database
    response = db.table("collections").insert(collection).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create collection")

    created_collection = response.data[0]
    created_collection["product_ids"] = []
    created_collection["product_slugs"] = []
    return created_collection


@router.post("/from-search", response_model=CollectionResponse, status_code=201)
async def create_collection_from_search(
    collection_data: CollectionFromSearchCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new collection and populate it with search results.

    Takes the same search parameters as GET /api/products and creates a collection
    with all matching products. The collection is automatically associated with the
    authenticated user.

    Security: Requires authentication; collection automatically associated with creator.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")
    user_name = current_user.get("username", "Unknown")

    # Validate input
    if not collection_data.name or not collection_data.name.strip():
        raise HTTPException(status_code=400, detail="Collection name is required")

    if collection_data.description and len(collection_data.description) > 1000:
        raise HTTPException(status_code=400, detail="Description must be 1000 characters or less")

    # Build search query using the same logic as GET /api/products
    query = db.table("products").select("id")

    # Normalize source filters
    source_values = set()
    if collection_data.source:
        source_values.update(collection_data.source)
    if collection_data.sources:
        source_values.update(collection_data.sources)

    # Canonicalize sources
    if source_values:
        try:
            rows = db.table("supported_sources").select("name").execute()
            name_map = {
                str(r.get("name")).strip().lower(): str(r.get("name")).strip()
                for r in (rows.data or [])
                if r.get("name")
            }
            canonical_sources = []
            for v in source_values:
                key = str(v).strip().lower()
                canonical_sources.append(name_map.get(key, v))
            # Deduplicate while preserving order
            seen = set()
            source_values = []
            for c in canonical_sources:
                if c not in seen:
                    seen.add(c)
                    source_values.append(c)
        except Exception as e:
            logger.error(f"error: {type(e).__name__}: {str(e)}")
            source_values = list(source_values)

        query = query.in_("source", source_values)

    # Normalize type filters
    type_values = set()
    if collection_data.type:
        type_values.update(collection_data.type)
    if collection_data.types:
        type_values.update(collection_data.types)

    if type_values:
        query = query.in_("type", list(type_values))

    # Handle tags
    if collection_data.tags:
        tag_mode = collection_data.tags_mode.lower()
        product_ids_with_tags = _get_product_ids_for_tags(db, collection_data.tags, tag_mode)
        if not product_ids_with_tags:
            # No products match the tag filter, create empty collection
            product_ids = []
        else:
            # Apply text search and other filters to tag-filtered products
            query = query.in_("id", list(product_ids_with_tags))

            if collection_data.search:
                query = query.ilike("name", f"%{collection_data.search}%")

            if collection_data.min_rating is not None:
                # For min_rating, we'll filter in Python after fetching all matches
                # since we need rating data
                query = query.eq("banned", False)
                query = query.order("created_at", desc=True)
                response = query.execute()
                products = response.data or []

                if products and collection_data.min_rating is not None:
                    # Build rating map
                    product_ids = [p.get("id") for p in products if p.get("id")]
                    if product_ids:
                        ratings_map = _build_display_rating_map(db, products)
                        product_ids = [
                            p.get("id")
                            for p in products
                            if p.get("id")
                            and _rating_meets_threshold(p, ratings_map, collection_data.min_rating)
                        ]
                    else:
                        product_ids = []
                else:
                    product_ids = [p.get("id") for p in products if p.get("id")]
            else:
                query = query.eq("banned", False)
                query = query.order("created_at", desc=True)
                response = query.execute()
                products = response.data or []
                product_ids = [p.get("id") for p in products if p.get("id")]
    else:
        # No tag filter, apply other filters directly
        if collection_data.search:
            query = query.ilike("name", f"%{collection_data.search}%")

        query = query.eq("banned", False)
        query = query.order("created_at", desc=True)
        response = query.execute()
        products = response.data or []
        product_ids = [p.get("id") for p in products if p.get("id")]

        # Apply min_rating filter if specified
        if collection_data.min_rating is not None and product_ids:
            ratings_map = _build_display_rating_map(db, products)
            product_ids = [
                p.get("id")
                for p in products
                if p.get("id")
                and _rating_meets_threshold(p, ratings_map, collection_data.min_rating)
            ]

    # Generate slug and create the collection
    slug = generate_id_with_uniqueness_check(collection_data.name, db, "collections", column="slug")

    collection_id = str(uuid.uuid4())
    collection = {
        "id": collection_id,
        "slug": slug,
        "user_id": user_id,
        "user_name": user_name,
        "name": collection_data.name,
        "description": collection_data.description,
        "is_public": collection_data.is_public,
    }

    # Insert collection into database
    response = db.table("collections").insert(collection).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create collection")

    # Insert products into junction table
    if product_ids:
        junction_records = [
            {"collection_id": collection_id, "product_id": pid, "position": idx}
            for idx, pid in enumerate(product_ids)
        ]
        try:
            db.table("collection_products").insert(junction_records).execute()
        except Exception as exc:
            # Best effort cleanup to avoid orphaned collection rows
            try:
                db.table("collections").delete().eq("id", collection_id).execute()
            except Exception:
                pass
            raise HTTPException(
                status_code=500, detail=f"Failed to populate collection from search: {str(exc)}"
            )

    # Return canonical response assembled from junction table data
    return _get_collection_with_products(db, collection_id)


def _get_product_ids_for_tags(db, tag_names: list[str], mode: str = "or") -> set[str]:
    """Return product IDs that match provided tag names using OR/AND semantics."""
    if not tag_names:
        return set()
    tag_rows = db.table("tags").select("id,name").in_("name", tag_names).execute()
    tag_map = {
        row["name"]: row["id"] for row in (tag_rows.data or []) if row.get("id") and row.get("name")
    }
    tag_ids = [tag_map[name] for name in tag_names if name in tag_map]
    if not tag_ids:
        return set()

    pt_rows = db.table("product_tags").select("product_id, tag_id").in_("tag_id", tag_ids).execute()
    if not pt_rows.data:
        return set()

    if mode == "and":
        required = set(tag_ids)
        product_tag_map: dict[str, set[str]] = {}
        for row in pt_rows.data:
            pid = row.get("product_id")
            tid = row.get("tag_id")
            if pid and tid:
                product_tag_map.setdefault(pid, set()).add(tid)
        return {pid for pid, tids in product_tag_map.items() if required.issubset(tids)}

    return {row["product_id"] for row in pt_rows.data if row.get("product_id")}


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _compute_display_rating(
    user_average: float | None, source_rating: float | None
) -> float | None:
    if user_average is not None and source_rating is not None:
        return (user_average + source_rating) / 2
    if user_average is not None:
        return user_average
    if source_rating is not None:
        return source_rating
    return None


def _build_display_rating_map(db, products: list[dict]) -> dict[str, dict]:
    """Compute display ratings and counts keyed by product ID."""
    product_ids = [p.get("id") for p in products if p.get("id")]
    if not product_ids:
        return {}

    # Fetch ratings for all products
    ratings_rows: list[dict] = []
    chunk_size = 500
    for i in range(0, len(product_ids), chunk_size):
        chunk = product_ids[i : i + chunk_size]
        resp = db.table("ratings").select("product_id,rating").in_("product_id", chunk).execute()
        ratings_rows.extend(resp.data or [])

    aggregates: dict[str, dict[str, float | int]] = {}
    for row in ratings_rows:
        pid = row.get("product_id")
        rating_raw = row.get("rating")
        rating_val = _safe_float(rating_raw)
        if not pid or rating_val is None:
            continue
        agg = aggregates.setdefault(pid, {"sum": 0.0, "count": 0})
        agg["sum"] += rating_val
        agg["count"] += 1

    ratings_map: dict[str, dict] = {}
    for product in products:
        pid = product.get("id")
        if not pid:
            continue
        agg = aggregates.get(pid, {"sum": 0.0, "count": 0})
        user_avg = (agg["sum"] / agg["count"]) if agg["count"] else None
        source_rating_val = _safe_float(product.get("source_rating"))
        display_rating = _compute_display_rating(user_avg, source_rating_val)
        ratings_map[pid] = {
            "average_rating": user_avg,
            "rating_count": agg.get("count", 0),
            "display_rating": display_rating,
        }
    return ratings_map


def _rating_meets_threshold(product: dict, ratings_map: dict[str, dict], min_rating: float) -> bool:
    rating_info = ratings_map.get(product.get("id"), {})
    display_rating = rating_info.get("display_rating")
    if display_rating is None:
        return False
    return display_rating >= min_rating


def _get_collection_with_products(db, collection_id: str) -> dict:
    """Fetch collection and populate product_ids and product_slugs from junction table."""
    collection_resp = db.table("collections").select("*").eq("id", collection_id).execute()
    if not collection_resp.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = collection_resp.data[0]

    # Get product IDs from junction table, ordered by position
    junction_resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection_id)
        .order("position")
        .execute()
    )
    product_ids = [p["product_id"] for p in (junction_resp.data or [])]

    # Get product slugs by querying products table with the IDs
    product_slugs = []
    if product_ids:
        products_resp = db.table("products").select("id, slug").in_("id", product_ids).execute()
        # Create a map of product_id -> slug for fast lookup
        id_to_slug = {p["id"]: p["slug"] for p in (products_resp.data or [])}
        # Build slugs list in the same order as product_ids
        product_slugs = [id_to_slug.get(pid, None) for pid in product_ids]

    collection["product_ids"] = product_ids
    collection["product_slugs"] = product_slugs

    return collection


def _get_collection_by_slug_or_id(db, slug_or_id: str) -> dict:
    """Fetch collection by slug; fall back to id."""
    resp = db.table("collections").select("*").eq("slug", slug_or_id).limit(1).execute()
    if resp.data:
        return resp.data[0]
    resp = db.table("collections").select("*").eq("id", slug_or_id).limit(1).execute()
    if resp.data:
        return resp.data[0]
    raise HTTPException(status_code=404, detail="Collection not found")


@router.get("", response_model=list[CollectionResponse])
async def get_user_collections(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all collections for the authenticated user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    # Fetch collections from database
    response = (
        db.table("collections")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    collections = response.data or []

    # Populate product_ids and product_slugs for each collection
    for collection in collections:
        products_resp = (
            db.table("collection_products")
            .select("product_id, products(slug)")
            .eq("collection_id", collection["id"])
            .order("position")
            .execute()
        )
        collection["product_ids"] = [p["product_id"] for p in (products_resp.data or [])]
        collection["product_slugs"] = [
            p["products"]["slug"] if p.get("products") else None for p in (products_resp.data or [])
        ]

    return collections


@router.get("/public", response_model=list[CollectionResponse])
async def get_public_collections(
    sort_by: str = Query("created_at", pattern=r"^(created_at|product_count|updated_at)$"),
    search: str | None = None,
    db=Depends(get_db),
):
    """Get all public collections, optionally sorted and filtered.

    Privacy: Only returns collections with is_public=true.
    Supports sorting by created_at (default), product_count, or updated_at.
    Optional search filters by collection name (case-insensitive).
    """
    # Fetch public collections
    response = db.table("collections").select("*").eq("is_public", True).execute()

    collections = response.data or []

    # Populate product_ids and product_slugs for each collection
    for collection in collections:
        products_resp = (
            db.table("collection_products")
            .select("product_id, products(slug)")
            .eq("collection_id", collection["id"])
            .order("position")
            .execute()
        )
        collection["product_ids"] = [p["product_id"] for p in (products_resp.data or [])]
        collection["product_slugs"] = [
            p["products"]["slug"] if p.get("products") else None for p in (products_resp.data or [])
        ]

    # Filter by search if provided
    if search:
        search_lower = search.lower()
        collections = [c for c in collections if search_lower in c.get("name", "").lower()]

    # Sort
    if sort_by == "product_count":
        collections.sort(key=lambda c: len(c.get("product_ids", []) or []), reverse=True)
    elif sort_by == "updated_at":
        collections.sort(key=lambda c: c.get("updated_at", c.get("created_at")), reverse=True)
    else:  # created_at
        collections.sort(key=lambda c: c.get("created_at"), reverse=True)

    return collections


@router.get("/{collection_slug}", response_model=CollectionResponse)
async def get_collection(
    collection_slug: str,
    request: Request,
    current_user: dict | None = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    """Get collection details by slug.

    Public collections viewable by all; private collections only by owner.
    """
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    # Check access
    if not collection.get("is_public"):
        if not current_user or current_user.get("id") != collection.get("user_id"):
            raise HTTPException(status_code=403, detail="Access denied")

    # Populate product_ids from junction table
    products_resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection["id"])
        .order("position")
        .execute()
    )
    collection["product_ids"] = [p["product_id"] for p in (products_resp.data or [])]

    return collection


@router.put("/{collection_slug}", response_model=CollectionResponse)
async def update_collection(
    collection_slug: str,
    collection_data: CollectionUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update collection by slug - only owner can edit."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    # Get collection
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    # Check ownership
    if collection.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can edit this collection")

    # Validate input
    if collection_data.name is not None:
        if not collection_data.name.strip():
            raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    if collection_data.description is not None and len(collection_data.description) > 1000:
        raise HTTPException(status_code=400, detail="Description must be 1000 characters or less")

    # Build update data
    collection_id = collection.get("id")
    update_data = {}
    if collection_data.name is not None:
        update_data["name"] = collection_data.name
        # Regenerate slug when name changes
        update_data["slug"] = generate_id_with_uniqueness_check(
            collection_data.name, db, "collections", column="slug"
        )
    if collection_data.description is not None:
        update_data["description"] = collection_data.description
    if collection_data.is_public is not None:
        update_data["is_public"] = collection_data.is_public

    update_data["updated_at"] = datetime.now(UTC).isoformat()

    # Update in database
    response = db.table("collections").update(update_data).eq("id", collection_id).execute()

    updated_collection = response.data[0]

    # Populate product_ids from junction table
    products_resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection_id)
        .order("position")
        .execute()
    )
    updated_collection["product_ids"] = [p["product_id"] for p in (products_resp.data or [])]

    return updated_collection


@router.delete("/{collection_slug}", status_code=204)
async def delete_collection(
    collection_slug: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete collection by slug - only owner can delete."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    # Check ownership
    if collection.get("user_id") != current_user.get("id"):
        raise HTTPException(status_code=403, detail="Only the owner can delete this collection")

    # Delete join table links first when available
    try:
        db.table("collection_products").delete().eq("collection_id", collection.get("id")).execute()
    except Exception:
        pass

    # Delete from database
    db.table("collections").delete().eq("id", collection.get("id")).execute()

    return None


@router.post("/{collection_slug}/products/{product_slug}", response_model=CollectionResponse)
async def add_product_to_collection(
    collection_slug: str,
    product_slug: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Add a product to a collection by slug."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    # Check ownership
    if collection.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can modify this collection")

    # Get product by slug or UUID
    if _looks_like_uuid(product_slug):
        products = db.table("products").select("id").eq("id", product_slug).execute()
    else:
        products = db.table("products").select("id").eq("slug", product_slug).execute()

    if not products.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product_id = products.data[0].get("id")

    # Check if product is already in collection (idempotent behavior)
    existing_resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection_id)
        .eq("product_id", product_id)
        .execute()
    )
    if existing_resp.data:
        # Product already in collection, return collection unchanged
        return _get_collection_with_products(db, collection_id)

    # Get current position for new product
    position_result = (
        db.table("collection_products")
        .select("position")
        .eq("collection_id", collection_id)
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    next_position = (position_result.data[0]["position"] + 1) if position_result.data else 0

    # Add product to junction table
    db.table("collection_products").insert(
        {"collection_id": collection_id, "product_id": product_id, "position": next_position}
    ).execute()

    # Update collection timestamp
    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

    # Return updated collection with product_ids
    return _get_collection_with_products(db, collection_id)


@router.delete("/{collection_slug}/products/{product_slug}", response_model=CollectionResponse)
async def remove_product_from_collection(
    collection_slug: str,
    product_slug: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Remove a product from a collection by slug."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    # Get product by slug or UUID
    if _looks_like_uuid(product_slug):
        product_response = db.table("products").select("id").eq("id", product_slug).execute()
    else:
        product_response = db.table("products").select("id").eq("slug", product_slug).execute()

    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product_id = product_response.data[0].get("id")

    # Check ownership
    if collection.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can modify this collection")

    # Remove product from junction table
    db.table("collection_products").delete().eq("collection_id", collection_id).eq(
        "product_id", product_id
    ).execute()

    # Update collection timestamp
    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

    # Return updated collection with product_ids
    return _get_collection_with_products(db, collection_id)


@router.delete("/{collection_slug}/products", response_model=CollectionResponse)
async def remove_all_products_from_collection(
    collection_slug: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Remove all products from a collection"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    # Check ownership
    if collection.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can modify this collection")

    # Clear all products from junction table
    db.table("collection_products").delete().eq("collection_id", collection_id).execute()

    # Update collection timestamp
    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

    # Return updated collection with empty product_ids
    return _get_collection_with_products(db, collection_id)


@router.post("/{collection_slug}/products", response_model=CollectionResponse)
async def add_multiple_products_to_collection(
    collection_slug: str,
    request: ProductIdsRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Add multiple products to a collection at once (product_ids can be UUIDs or slugs)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")
    product_ids = request.product_ids

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    # Check ownership
    if collection.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can modify this collection")

    # Idempotent behavior: Empty list is allowed (returns collection unchanged)
    if not product_ids:
        return _get_collection_with_products(db, collection_id)

    # Resolve product slugs/UUIDs to IDs
    resolved_product_ids = []
    for prod_identifier in product_ids:
        # Try as UUID first, then as slug
        if _looks_like_uuid(prod_identifier):
            products = db.table("products").select("id").eq("id", prod_identifier).execute()
        else:
            products = db.table("products").select("id").eq("slug", prod_identifier).execute()

        if products.data:
            resolved_product_ids.append(products.data[0].get("id"))
        else:
            raise HTTPException(status_code=404, detail=f"Product {prod_identifier} not found")

    # Deduplicate the resolved product IDs (in case request had duplicates)
    # Preserve order while removing duplicates
    seen = set()
    deduplicated_product_ids = []
    for pid in resolved_product_ids:
        if pid not in seen:
            seen.add(pid)
            deduplicated_product_ids.append(pid)

    # Get current product IDs from junction table
    current_resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection_id)
        .execute()
    )
    existing_product_ids = {p["product_id"] for p in (current_resp.data or [])}

    # Add new products to junction table (avoiding duplicates)
    new_products = [pid for pid in deduplicated_product_ids if pid not in existing_product_ids]

    if new_products:
        # Get current max position
        position_result = (
            db.table("collection_products")
            .select("position")
            .eq("collection_id", collection_id)
            .order("position", desc=True)
            .limit(1)
            .execute()
        )
        next_position = (position_result.data[0]["position"] + 1) if position_result.data else 0

        # Insert new products
        junction_records = [
            {"collection_id": collection_id, "product_id": pid, "position": next_position + idx}
            for idx, pid in enumerate(new_products)
        ]
        db.table("collection_products").insert(junction_records).execute()

        # Update collection timestamp
        db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
            "id", collection_id
        ).execute()

    # Return updated collection
    return _get_collection_with_products(db, collection_id)
