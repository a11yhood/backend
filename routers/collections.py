"""Collection management endpoints.

Supports user-curated product collections with public/private visibility.
All mutations require authentication and enforce owner/editor checks.
Security: Owners and assigned editors can modify collections; admins and moderators
can manage collection editor assignments.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import TypeAdapter

from models.collections import (
    CollectionCreate,
    CollectionEditorsResponse,
    CollectionEntry,
    CollectionFromSearchCreate,
    CollectionResponse,
    CollectionUpdate,
    ProductIdsRequest,
)
from services.auth import get_current_user, get_current_user_optional
from services.database import get_db, wait_for_row_visibility
from services.id_generator import generate_id_with_uniqueness_check
from services.product_queries import fetch_filtered_product_ids, prepare_product_filters
from services.ratings import compute_display_rating

router = APIRouter(prefix="/api/collections", tags=["collections"])
logger = logging.getLogger(__name__)
_COLLECTION_ENTRIES_TABLE_AVAILABLE: bool | None = None
_COLLECTION_ENTRY_ADAPTER = TypeAdapter(CollectionEntry)


def _is_collection_entries_missing_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "collection_entries" in message
        and (
            "does not exist" in message
            or "undefined table" in message
            or "42p01" in message
        )
    )


def _is_rpc_not_found_error(exc: Exception) -> bool:
    """True when the DB reports that the replace_collection_entries RPC does not exist."""
    message = str(exc).lower()
    return (
        "replace_collection_entries" in message
        or "pgrst202" in message
        or (
            "could not find" in message
            and "function" in message
        )
    )


def _looks_like_uuid(value: str) -> bool:
    """Check if a string looks like a UUID."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _is_collection_editor(db, collection_id: str, user_id: str | None) -> bool:
    if not collection_id or not user_id:
        return False
    try:
        editors_response = (
            db.table("collection_editors")
            .select("user_id")
            .eq("collection_id", collection_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(editors_response.data)
    except Exception as e:
        logger.error(f"collection editor check error: {type(e).__name__}: {str(e)}")
        return False


def _can_edit_collection(db, collection: dict, current_user: dict | None) -> bool:
    """True when user is the collection owner or an assigned editor."""
    if not collection or not current_user:
        return False
    user_id = current_user.get("id")
    if collection.get("user_id") == user_id:
        return True
    return _is_collection_editor(db, collection.get("id"), user_id)


def _can_manage_collection_editors(collection: dict, current_user: dict | None) -> bool:
    """True when user can add/remove editors: owner, admin, or moderator."""
    if not collection or not current_user:
        return False
    if collection.get("user_id") == current_user.get("id"):
        return True
    return current_user.get("role") in {"admin", "moderator"}


def _extract_non_owner_editor_ids(editor_rows: list[dict], owner_user_id: str | None) -> list[str]:
    """Return editor user IDs excluding the owner, who is represented by `user_id`."""
    return [
        row["user_id"]
        for row in editor_rows
        if row.get("user_id") and row.get("user_id") != owner_user_id
    ]


def _collection_entries_table_available(db) -> bool:
    global _COLLECTION_ENTRIES_TABLE_AVAILABLE
    if _COLLECTION_ENTRIES_TABLE_AVAILABLE is not None:
        return _COLLECTION_ENTRIES_TABLE_AVAILABLE

    try:
        db.table("collection_entries").select("id").limit(1).execute()
        _COLLECTION_ENTRIES_TABLE_AVAILABLE = True
    except Exception as exc:
        if _is_collection_entries_missing_error(exc):
            # Don't cache False — the migration may be applied while the server is running.
            return False
        logger.warning(
            "collection_entries availability check failed transiently; not caching: %s",
            exc,
        )
        raise
    return _COLLECTION_ENTRIES_TABLE_AVAILABLE


def _validate_no_duplicate_entries(entries: list) -> None:
    """Raise 400 if the entries list contains duplicates by kind+id."""
    seen: dict[str, set[str]] = {}
    for entry in entries:
        kind = getattr(entry, "kind", None)
        if kind == "product":
            key = getattr(entry, "product_id", None)
        elif kind == "collection":
            key = getattr(entry, "collection_id", None)
        elif kind == "blogPost":
            key = getattr(entry, "blog_post_id", None)
        else:
            continue
        if key is None:
            continue
        if key in seen.get(kind, set()):
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate {kind} entry: {key}",
            )
        seen.setdefault(kind, set()).add(key)


def _existing_product_ids_in_collection(db, collection_id: str) -> set[str]:
    """Return product IDs already in the collection, checking collection_entries when available."""
    if _collection_entries_table_available(db):
        try:
            resp = (
                db.table("collection_entries")
                .select("product_id")
                .eq("collection_id", collection_id)
                .eq("kind", "product")
                .execute()
            )
            return {row["product_id"] for row in (resp.data or []) if row.get("product_id")}
        except Exception:
            pass
    resp = (
        db.table("collection_products")
        .select("product_id")
        .eq("collection_id", collection_id)
        .execute()
    )
    return {row["product_id"] for row in (resp.data or []) if row.get("product_id")}


def _get_next_entry_position(db, collection_id: str) -> int:
    """Return the next available position for a new entry, using collection_entries when available."""
    if _collection_entries_table_available(db):
        try:
            resp = (
                db.table("collection_entries")
                .select("position")
                .eq("collection_id", collection_id)
                .order("position", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                return (resp.data[0].get("position") or 0) + 1
            return 0
        except Exception:
            pass
    resp = (
        db.table("collection_products")
        .select("position")
        .eq("collection_id", collection_id)
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    return (resp.data[0]["position"] + 1) if resp.data else 0


def _entries_from_product_ids(product_ids: list[str]) -> list[dict]:
    return [
        {"kind": "product", "product_id": product_id, "position": position}
        for position, product_id in enumerate(product_ids)
    ]


def _sync_collection_products_from_entries(db, collection_id: str, entries: list[CollectionEntry]) -> None:
    product_entries = [entry for entry in entries if getattr(entry, "kind", None) == "product"]

    db.table("collection_products").delete().eq("collection_id", collection_id).execute()
    if not product_entries:
        return

    rows = [
        {
            "collection_id": collection_id,
            "product_id": entry.product_id,
            "position": idx,
        }
        for idx, entry in enumerate(product_entries)
    ]
    db.table("collection_products").insert(rows).execute()


def _replace_collection_entries(db, collection_id: str, entries: list[CollectionEntry]) -> None:
    if not _collection_entries_table_available(db):
        non_product_entries = [entry for entry in entries if getattr(entry, "kind", None) != "product"]
        if non_product_entries:
            raise HTTPException(
                status_code=400,
                detail="Non-product collection entries require the collection_entries migration",
            )
        _sync_collection_products_from_entries(db, collection_id, entries)
        return

    entries_payload = [entry.model_dump(exclude_none=True) for entry in entries]

    try:
        db.rpc(
            "replace_collection_entries",
            {
                "p_collection_id": collection_id,
                "p_entries": entries_payload,
            },
        ).execute()
        return
    except Exception as exc:
        if not _is_rpc_not_found_error(exc):
            raise
        # RPC not yet deployed — fall through to manual path.

    db.table("collection_entries").delete().eq("collection_id", collection_id).execute()

    if entries:
        entry_rows = []
        for idx, entry in enumerate(entries):
            row = {
                "collection_id": collection_id,
                "kind": entry.kind,
                "position": idx,
                "label": entry.label,
                "product_id": None,
                "collection_ref_id": None,
                "blog_post_id": None,
                "query_json": None,
            }
            if entry.kind == "product":
                row["product_id"] = entry.product_id
            elif entry.kind == "collection":
                row["collection_ref_id"] = entry.collection_id
            elif entry.kind == "blogPost":
                row["blog_post_id"] = entry.blog_post_id
            elif entry.kind == "query":
                row["query_json"] = entry.query.model_dump(exclude_none=True)
            entry_rows.append(row)

        db.table("collection_entries").insert(entry_rows).execute()

    _sync_collection_products_from_entries(db, collection_id, entries)


def _load_collection_entries_map(db, collection_ids: list[str]) -> dict[str, list[dict]]:
    if not collection_ids:
        return {}

    if not _collection_entries_table_available(db):
        return {}

    try:
        response = (
            db.table("collection_entries")
            .select(
                "collection_id,kind,position,label,product_id,collection_ref_id,blog_post_id,query_json"
            )
            .in_("collection_id", collection_ids)
            .order("position")
            .execute()
        )
    except Exception as exc:
        logger.warning("Failed to load collection entries for %s: %s", collection_ids, exc)
        return {}

    entries_map: dict[str, list[dict]] = {}
    for row in (response.data or []):
        collection_id = row.get("collection_id")
        if not collection_id:
            continue

        entry = {
            "kind": row.get("kind"),
            "position": row.get("position") or 0,
            "label": row.get("label"),
        }
        kind = row.get("kind")
        if kind == "product":
            entry["product_id"] = row.get("product_id")
        elif kind == "collection":
            entry["collection_id"] = row.get("collection_ref_id")
        elif kind == "blogPost":
            entry["blog_post_id"] = row.get("blog_post_id")
        elif kind == "query":
            entry["query"] = row.get("query_json") or {}

        entries_map.setdefault(collection_id, []).append(entry)

    return entries_map


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

    if collection_data.entries:
        _validate_no_duplicate_entries(collection_data.entries)

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
    if user_id and not wait_for_row_visibility(db, "users", "id", user_id, select="id", attempts=2):
        db.table("users").upsert(
            {
                "id": user_id,
                "github_id": current_user.get("github_id") or f"rehydrated-{user_id[:8]}",
                "username": current_user.get("username") or f"user_{user_id[:8]}",
                "display_name": current_user.get("display_name") or user_name,
                "email": current_user.get("email") or f"{user_id[:8]}@a11yhood.test",
                "role": current_user.get("role") or "user",
            },
            on_conflict="id",
        ).execute()

    response = db.table("collections").insert(collection).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create collection")

    created_collection = response.data[0]
    created_collection = (
        wait_for_row_visibility(db, "collections", "id", created_collection["id"])
        or created_collection
    )
    entries_payload = collection_data.entries or []
    if entries_payload:
        try:
            _replace_collection_entries(db, created_collection["id"], entries_payload)
        except Exception:
            try:
                db.table("collections").delete().eq("id", created_collection["id"]).execute()
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to clean up collection %s after entry replacement error: %s",
                    created_collection["id"],
                    cleanup_exc,
                )
            raise

    return _get_collection_with_products(db, created_collection["id"])


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

    filters = prepare_product_filters(db, current_user, collection_data, allow_aliases=True)
    product_ids = fetch_filtered_product_ids(db, filters, sort_field="created_at", sort_desc=True)
    entries_payload = _entries_from_product_ids(product_ids)

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

    if user_id and not wait_for_row_visibility(db, "users", "id", user_id, select="id", attempts=2):
        db.table("users").upsert(
            {
                "id": user_id,
                "github_id": current_user.get("github_id") or f"rehydrated-{user_id[:8]}",
                "username": current_user.get("username") or f"user_{user_id[:8]}",
                "display_name": current_user.get("display_name") or user_name,
                "email": current_user.get("email") or f"{user_id[:8]}@a11yhood.test",
                "role": current_user.get("role") or "user",
            },
            on_conflict="id",
        ).execute()

    # Insert collection into database
    response = db.table("collections").insert(collection).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create collection")

    try:
        _replace_collection_entries(
            db,
            collection_id,
            [_COLLECTION_ENTRY_ADAPTER.validate_python(entry) for entry in entries_payload],
        )
    except Exception as exc:
        # Best effort cleanup to avoid orphaned collection rows
        try:
            db.table("collections").delete().eq("id", collection_id).execute()
        except Exception as cleanup_exc:
            logger.warning(
                "Failed to cleanup collection %s after populate error: %s",
                collection_id,
                cleanup_exc,
            )

        if isinstance(exc, HTTPException):
            raise exc

        raise HTTPException(
            status_code=500,
            detail=f"Failed to populate collection from search: {str(exc)}",
        )

    # Return canonical response assembled from junction table data
    return _get_collection_with_products(db, collection_id)


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _compute_display_rating(
    user_average: float | None,
    source_rating: float | None,
    user_rating_count: int = 0,
) -> float | None:
    return compute_display_rating(user_average, source_rating, user_rating_count)


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
        user_count = int(agg["count"]) if agg.get("count") else 0
        user_avg = (agg["sum"] / user_count) if user_count else None
        source_rating_val = _safe_float(product.get("source_rating"))
        display_rating = _compute_display_rating(user_avg, source_rating_val, user_count)
        ratings_map[pid] = {
            "average_rating": user_avg,
            "rating_count": user_count,
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
    _populate_collection_relationships(db, collection)
    return collection


def _populate_collection_relationships(db, collection: dict) -> dict:
    """Attach editor and product relationship fields expected by the API response model."""
    _populate_collection_relationships_bulk(db, [collection])
    return collection


def _populate_collection_relationships_bulk(db, collections: list[dict]) -> list[dict]:
    """Populate editor_ids, product_ids, and product_slugs for many collections in bulk."""
    if not collections:
        return collections

    collection_ids = [c["id"] for c in collections if c.get("id")]
    if not collection_ids:
        return collections

    owner_by_collection = {c["id"]: c.get("user_id") for c in collections if c.get("id")}

    editors_resp = (
        db.table("collection_editors")
        .select("collection_id, user_id")
        .in_("collection_id", collection_ids)
        .execute()
    )
    editors_by_collection: dict[str, list[dict]] = {}
    for row in (editors_resp.data or []):
        collection_id = row.get("collection_id")
        if not collection_id:
            continue
        editors_by_collection.setdefault(collection_id, []).append(row)

    junction_resp = (
        db.table("collection_products")
        .select("collection_id, product_id, position")
        .in_("collection_id", collection_ids)
        .execute()
    )
    product_rows_by_collection: dict[str, list[dict]] = {}
    for row in (junction_resp.data or []):
        collection_id = row.get("collection_id")
        if not collection_id:
            continue
        product_rows_by_collection.setdefault(collection_id, []).append(row)

    entry_map = _load_collection_entries_map(db, collection_ids)

    all_product_ids = {
        row["product_id"]
        for rows in product_rows_by_collection.values()
        for row in rows
        if row.get("product_id")
    }
    for rows in entry_map.values():
        for entry in rows:
            if entry.get("kind") == "product" and entry.get("product_id"):
                all_product_ids.add(entry["product_id"])
    id_to_slug: dict[str, str] = {}
    if all_product_ids:
        products_resp = db.table("products").select("id, slug").in_("id", list(all_product_ids)).execute()
        id_to_slug = {p["id"]: p["slug"] for p in (products_resp.data or []) if p.get("id")}

    for collection in collections:
        collection_id = collection.get("id")
        if not collection_id:
            collection["editor_ids"] = []
            collection["product_ids"] = []
            collection["product_slugs"] = []
            collection["entries"] = []
            continue

        editor_rows = editors_by_collection.get(collection_id, [])
        collection["editor_ids"] = _extract_non_owner_editor_ids(
            editor_rows,
            owner_by_collection.get(collection_id),
        )

        stored_entries = entry_map.get(collection_id, [])
        if stored_entries:
            entries = sorted(
                stored_entries,
                key=lambda entry: (entry.get("position") is None, entry.get("position", 0)),
            )
            collection["entries"] = entries
            product_ids = [
                entry["product_id"]
                for entry in entries
                if entry.get("kind") == "product" and entry.get("product_id")
            ]
        else:
            product_rows = sorted(
                product_rows_by_collection.get(collection_id, []),
                key=lambda row: (row.get("position") is None, row.get("position", 0)),
            )
            product_ids = [row["product_id"] for row in product_rows if row.get("product_id")]
            collection["entries"] = _entries_from_product_ids(product_ids)

        collection["product_ids"] = product_ids
        collection["product_slugs"] = [id_to_slug.get(pid, None) for pid in product_ids]

    return collections


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
    """Get collections the authenticated user can manage.

    Returns both:
    - collections owned by the user (`access_role=owner`)
    - collections where the user is an assigned editor (`access_role=editor`)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = current_user.get("id")

    owned_response = (
        db.table("collections")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    editor_links_response = (
        db.table("collection_editors")
        .select("collection_id")
        .eq("user_id", user_id)
        .execute()
    )
    editor_collection_ids = [
        row["collection_id"]
        for row in (editor_links_response.data or [])
        if row.get("collection_id")
    ]

    editor_collections: list[dict] = []
    if editor_collection_ids:
        editor_collections_response = (
            db.table("collections")
            .select("*")
            .in_("id", editor_collection_ids)
            .execute()
        )
        editor_collections = editor_collections_response.data or []

    collections_by_id: dict[str, dict] = {}
    for collection in (owned_response.data or []):
        collection_id = collection.get("id")
        if collection_id:
            collection["access_role"] = "owner"
            collection["is_owner"] = True
            collections_by_id[collection_id] = collection

    for collection in editor_collections:
        collection_id = collection.get("id")
        if not collection_id:
            continue
        if collection_id in collections_by_id:
            # Owner precedence for any data inconsistencies where owner is also listed as editor.
            continue
        collection["access_role"] = "editor"
        collection["is_owner"] = False
        collections_by_id[collection_id] = collection

    collections = list(collections_by_id.values())
    collections.sort(key=lambda collection: collection.get("created_at") or "", reverse=True)

    # Populate relationship fields in bulk to avoid N+1 round-trips.
    _populate_collection_relationships_bulk(db, collections)

    return collections


@router.get("/public", response_model=list[CollectionResponse])
async def get_public_collections(
    sort_by: str = Query("created_at", pattern=r"^(created_at|product_count|updated_at)$"),
    search: str | None = None,
    editor_id: str | None = Query(None, description="Filter by collection owner/editor user ID"),
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

    # Populate relationship fields in bulk to avoid N+1 round-trips.
    _populate_collection_relationships_bulk(db, collections)

    # Filter by search if provided
    if search:
        search_lower = search.lower()
        collections = [
            c
            for c in collections
            if search_lower in c.get("name", "").lower()
            or search_lower in (c.get("description") or "").lower()
        ]

    if editor_id:
        collections = [
            c
            for c in collections
            if c.get("user_id") == editor_id or editor_id in (c.get("editor_ids") or [])
        ]

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

    Public collections are viewable by all; private collections require owner or editor access.
    """
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    # Check access
    if not collection.get("is_public"):
        if not current_user or not _can_edit_collection(db, collection, current_user):
            raise HTTPException(status_code=403, detail="Access denied")

    return _populate_collection_relationships(db, collection)


@router.put("/{collection_slug}", response_model=CollectionResponse)
async def update_collection(
    collection_slug: str,
    collection_data: CollectionUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update collection by slug. Allowed for owner or assigned editor."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get collection
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(status_code=403, detail="Only owners and editors can update this collection")

    # Validate input
    if collection_data.name is not None:
        if not collection_data.name.strip():
            raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    if collection_data.description is not None and len(collection_data.description) > 1000:
        raise HTTPException(status_code=400, detail="Description must be 1000 characters or less")

    if collection_data.entries is not None:
        _validate_no_duplicate_entries(collection_data.entries)

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

    if not response.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection_data.entries is not None:
        _replace_collection_entries(db, collection_id, collection_data.entries)

    return _get_collection_with_products(db, collection_id)


@router.get("/{collection_slug}/editors", response_model=CollectionEditorsResponse)
async def get_collection_editors(
    collection_slug: str,
    current_user: dict | None = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    """Return editor IDs for a collection.

    Public collections expose editor IDs publicly. Private collections require owner/editor access.
    """
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    if not collection.get("is_public"):
        if not current_user or not _can_edit_collection(db, collection, current_user):
            raise HTTPException(status_code=403, detail="Access denied")

    editors_resp = (
        db.table("collection_editors")
        .select("user_id")
        .eq("collection_id", collection["id"])
        .execute()
    )
    return {
        "collection_id": collection["id"],
        "editor_ids": _extract_non_owner_editor_ids(
            editors_resp.data or [], collection.get("user_id")
        ),
    }


@router.post("/{collection_slug}/editors/{editor_user_id}", response_model=CollectionResponse)
async def add_collection_editor(
    collection_slug: str,
    editor_user_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Add an editor to a collection.

    Allowed for collection owner, admin, or moderator.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _looks_like_uuid(editor_user_id):
        raise HTTPException(status_code=400, detail="Invalid editor user id")

    collection = _get_collection_by_slug_or_id(db, collection_slug)
    if not _can_manage_collection_editors(collection, current_user):
        raise HTTPException(status_code=403, detail="Only owners, moderators, and admins can manage editors")
    if editor_user_id == collection.get("user_id"):
        raise HTTPException(status_code=400, detail="Collection owner is not an editor")

    user_resp = db.table("users").select("id").eq("id", editor_user_id).limit(1).execute()
    if not user_resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    db.table("collection_editors").upsert(
        {"collection_id": collection["id"], "user_id": editor_user_id},
        on_conflict="collection_id,user_id",
    ).execute()

    return _get_collection_with_products(db, collection["id"])


@router.delete("/{collection_slug}/editors/{editor_user_id}", response_model=CollectionResponse)
async def remove_collection_editor(
    collection_slug: str,
    editor_user_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Remove an editor from a collection.

    Allowed for collection owner, admin, or moderator. Owner cannot be removed.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _looks_like_uuid(editor_user_id):
        raise HTTPException(status_code=400, detail="Invalid editor user id")

    collection = _get_collection_by_slug_or_id(db, collection_slug)
    if not _can_manage_collection_editors(collection, current_user):
        raise HTTPException(status_code=403, detail="Only owners, admins, or moderators can manage editors")

    if editor_user_id == collection.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot remove the collection owner")

    db.table("collection_editors").delete().eq("collection_id", collection["id"]).eq(
        "user_id", editor_user_id
    ).execute()

    return _get_collection_with_products(db, collection["id"])


@router.delete("/{collection_slug}", status_code=204)
async def delete_collection(
    collection_slug: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete collection by slug - owner or editor can delete."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    collection = _get_collection_by_slug_or_id(db, collection_slug)

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(
            status_code=403, detail="Only owners and editors can delete this collection"
        )

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

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(
            status_code=403, detail="Only owners and editors can modify this collection"
        )

    # Get product by slug or UUID
    if _looks_like_uuid(product_slug):
        products = db.table("products").select("id").eq("id", product_slug).execute()
    else:
        products = db.table("products").select("id").eq("slug", product_slug).execute()

    if not products.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product_id = products.data[0].get("id")

    if product_id in _existing_product_ids_in_collection(db, collection_id):
        raise HTTPException(status_code=409, detail="Product is already in this collection")

    next_position = _get_next_entry_position(db, collection_id)

    if _collection_entries_table_available(db):
        db.table("collection_entries").insert(
            {
                "collection_id": collection_id,
                "kind": "product",
                "position": next_position,
                "label": None,
                "product_id": product_id,
                "collection_ref_id": None,
                "blog_post_id": None,
                "query_json": None,
            }
        ).execute()

    db.table("collection_products").insert(
        {"collection_id": collection_id, "product_id": product_id, "position": next_position}
    ).execute()

    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

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

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(
            status_code=403, detail="Only owners and editors can modify this collection"
        )

    if _collection_entries_table_available(db):
        db.table("collection_entries").delete().eq("collection_id", collection_id).eq(
            "kind", "product"
        ).eq("product_id", product_id).execute()

    db.table("collection_products").delete().eq("collection_id", collection_id).eq(
        "product_id", product_id
    ).execute()

    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

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

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(
            status_code=403, detail="Only owners and editors can modify this collection"
        )

    if _collection_entries_table_available(db):
        db.table("collection_entries").delete().eq("collection_id", collection_id).eq(
            "kind", "product"
        ).execute()

    db.table("collection_products").delete().eq("collection_id", collection_id).execute()

    db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
        "id", collection_id
    ).execute()

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

    product_ids = request.product_ids

    # Get collection by slug or id
    collection = _get_collection_by_slug_or_id(db, collection_slug)
    collection_id = collection.get("id")

    if not _can_edit_collection(db, collection, current_user):
        raise HTTPException(
            status_code=403, detail="Only owners and editors can modify this collection"
        )

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

    existing_product_ids = _existing_product_ids_in_collection(db, collection_id)

    already_present = [pid for pid in deduplicated_product_ids if pid in existing_product_ids]
    if already_present:
        raise HTTPException(
            status_code=409,
            detail=f"Products already in collection: {', '.join(already_present)}",
        )

    if deduplicated_product_ids:
        next_position = _get_next_entry_position(db, collection_id)

        if _collection_entries_table_available(db):
            entry_rows = [
                {
                    "collection_id": collection_id,
                    "kind": "product",
                    "position": next_position + idx,
                    "label": None,
                    "product_id": pid,
                    "collection_ref_id": None,
                    "blog_post_id": None,
                    "query_json": None,
                }
                for idx, pid in enumerate(deduplicated_product_ids)
            ]
            db.table("collection_entries").insert(entry_rows).execute()

        junction_records = [
            {"collection_id": collection_id, "product_id": pid, "position": next_position + idx}
            for idx, pid in enumerate(deduplicated_product_ids)
        ]
        db.table("collection_products").insert(junction_records).execute()

        db.table("collections").update({"updated_at": datetime.now(UTC).isoformat()}).eq(
            "id", collection_id
        ).execute()

    # Return updated collection
    return _get_collection_with_products(db, collection_id)
