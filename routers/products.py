"""Product management endpoints.

Handles CRUD operations for products with ownership tracking via product_editors table.
Supports URL-based upsert for scrapers and tag management via relationship tables.
Security: Mutations require authentication; updates/deletes enforce ownership or admin role.
"""
import os
import uuid
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from typing import Optional, Iterable, Any
from datetime import datetime, UTC, timedelta
import httpx

from pydantic import BaseModel

from config import settings
from models.products import ProductCreate, ProductUpdate, ProductResponse
from services.database import get_db
from services.auth import get_current_user, get_current_user_optional
from services.id_generator import generate_id_with_uniqueness_check
from services.sources import extract_domain, find_source_for_domain

router = APIRouter(prefix="/api/products", tags=["products"])


def _normalize_list(values: Optional[Iterable[str] | str]) -> list[str]:
    """Flatten query params supporting comma-separated and repeated values."""
    normalized: list[str] = []
    if values is None:
        return normalized
    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = values
    for v in raw_values:
        if v is None:
            continue
        if not isinstance(v, str):
            v = str(v)
        for part in v.split(","):
            item = part.strip()
            if item:
                normalized.append(item)
    return normalized


def _looks_like_uuid(value: str) -> bool:
    """Check if a string resembles a UUID (best-effort, non-raising)."""
    try:
        uuid.UUID(str(value))
        return True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"uuid error: {type(e).__name__}: {str(e)}")
        return False


def _canonicalize_sources(db, values: list[str]) -> list[str]:
    """Map incoming source filter values to canonical names from supported_sources (case-insensitive).

    Example: 'github' -> 'Github' if supported_sources.name is 'Github'.
    Falls back to original input when no match is found.
    """
    if not values:
        return []
    try:
        rows = db.table("supported_sources").select("name").execute()
        name_map = {str(r.get("name")).strip().lower(): str(r.get("name")).strip() for r in (rows.data or []) if r.get("name")}
        canon: list[str] = []
        for v in values:
            key = str(v).strip().lower()
            canon.append(name_map.get(key, v))
        # Deduplicate while preserving order
        seen = set()
        unique: list[str] = []
        for c in canon:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique
    except Exception:
        logger = logging.getLogger(__name__)
        logger.error(f"Exception: {type(e).__name__}: {str(e)}")
        return values

def _get_supported_source_name_map(db) -> dict[str, str]:
    """Return mapping of lowercase source name -> canonical name from supported_sources."""
    try:
        rows = db.table("supported_sources").select("name").execute()
        return {str(r.get("name")).strip().lower(): str(r.get("name")).strip() for r in (rows.data or []) if r.get("name")}
    except Exception:
        logger = logging.getLogger(__name__)
        logger.error(f"Supported Source Exception: {type(e).__name__}: {str(e)}")
        return {}

def _canonicalize_source_value_db(db, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().lower()
    name_map = _get_supported_source_name_map(db)
    return name_map.get(key, value)


def _get_product_by_identifier(db, identifier: str) -> Optional[dict]:
    """Fetch a product by ID or slug without triggering UUID parse errors."""
    if _looks_like_uuid(identifier):
        resp = db.table("products").select("*").eq("id", identifier).limit(1).execute()
        if resp.data:
            return resp.data[0]
    resp = db.table("products").select("*").eq("slug", identifier).limit(1).execute()
    return resp.data[0] if resp.data else None


async def _enrich_manual_product_metadata(db, source_name: str, source_url: str, product: ProductCreate, db_data: dict):
    """Fetch metadata from source scrapers for manually submitted products.

    Best-effort: silently continue if tokens are missing or scraping fails.
    Populates source_last_updated and enriches description/image/external_id/ratings when available.
    """
    if not source_name or not source_url:
        return

    source_key = str(source_name).strip().lower()

    def _get_token(platform: str, env_keys: list[str]) -> Optional[str]:
        token = None
        try:
            resp = db.table("oauth_configs").select("access_token").eq("platform", platform).limit(1).execute()
            token = (resp.data or [{}])[0].get("access_token")
        except Exception:
            logger = logging.getLogger(__name__)
            logger.error(f"Get Token Exception: {type(e).__name__}: {str(e)}")
            token = None
        if not token:
            for key in env_keys:
                token = os.getenv(key)
                if token:
                    break
        return token

    scraper_map = {
        "thingiverse": {
            "platform": "thingiverse",
            "factory": lambda token: __import__("scrapers.thingiverse", fromlist=["ThingiverseScraper"]).ThingiverseScraper(db, token),
            "env_keys": ["THINGIVERSE_ACCESS_TOKEN", "THINGIVERSE_TOKEN"],
            "requires_token": True,
        },
        "github": {
            "platform": "github",
            "factory": lambda token: __import__("scrapers.github", fromlist=["GitHubScraper"]).GitHubScraper(db, token),
            "env_keys": ["GITHUB_TOKEN", "GITHUB_ACCESS_TOKEN"],
            "requires_token": False,
        },
        "ravelry": {
            "platform": "ravelry",
            "factory": lambda token: __import__("scrapers.ravelry", fromlist=["RavelryScraper"]).RavelryScraper(db, token),
            "env_keys": ["RAVELRY_ACCESS_TOKEN", "RAVELRY_APP_KEY"],
            "requires_token": True,
        },
        "goat": {
            "platform": "goat",
            "factory": lambda token: __import__("scrapers.goat", fromlist=["GOATScraper"]).GOATScraper(db, token),
            "env_keys": ["GOAT_API_KEY", "LIBRARYTHING_API_KEY", "LIBRARYTHING_TOKEN"],
            "requires_token": False,
        },
        "librarything": {
            "platform": "goat",
            "factory": lambda token: __import__("scrapers.goat", fromlist=["GOATScraper"]).GOATScraper(db, token),
            "env_keys": ["GOAT_API_KEY", "LIBRARYTHING_API_KEY", "LIBRARYTHING_TOKEN"],
            "requires_token": False,
        },
    }

    config = scraper_map.get(source_key)
    if not config:
        return

    token = _get_token(config["platform"], config["env_keys"])
    if config["requires_token"] and not token:
        return

    scraper = None
    try:
        scraper = config["factory"](token)
        scraped_data = await scraper.scrape_url(source_url)
        if not scraped_data:
            return
        # Populate fields when present
        if scraped_data.get("source_last_updated"):
            db_data["source_last_updated"] = scraped_data["source_last_updated"]
        if scraped_data.get("image_alt"):
            db_data["image_alt"] = scraped_data["image_alt"]
        if not product.description and scraped_data.get("description"):
            db_data["description"] = scraped_data["description"]
        if not product.image_url and scraped_data.get("image"):
            db_data["image"] = scraped_data["image"]
        if scraped_data.get("external_id"):
            db_data["external_id"] = scraped_data["external_id"]
        if scraped_data.get("source_rating"):
            db_data["source_rating"] = scraped_data["source_rating"]
        if scraped_data.get("source_rating_count"):
            db_data["source_rating_count"] = scraped_data["source_rating_count"]
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to fetch metadata for source '{source_name}': {e}")
    finally:
        try:
            if scraper and hasattr(scraper, "close"):
                await scraper.close()
        except Exception:
            logger = logging.getLogger(__name__)
            logger.error(f"Exception: {e}")
            pass


class BulkDeleteRequest(BaseModel):
    source: Optional[str | list[str]] = None
    sources: Optional[str | list[str]] = None
    type: Optional[str | list[str]] = None
    types: Optional[str | list[str]] = None
    tags: Optional[str | list[str]] = None
    tags_mode: Optional[str] = None
    min_rating: Optional[float] = None
    updated_since: Optional[str] = None
    max_age: Optional[int] = None
    search: Optional[str] = None
    created_by: Optional[str] = None
    include_banned: Optional[bool] = None
    product_ids: Optional[str | list[str]] = None


def _prepare_product_filters(
    db,
    current_user: Optional[dict],
    *,
    source: Optional[Iterable[str] | str] = None,
    sources: Optional[Iterable[str] | str] = None,
    type: Optional[Iterable[str] | str] = None,
    types: Optional[Iterable[str] | str] = None,
    tags: Optional[Iterable[str] | str] = None,
    tags_mode: str = "or",
    min_rating: Optional[float] = None,
    updated_since: Optional[str] = None,
    max_age: Optional[int] = None,
    search: Optional[str] = None,
    created_by: Optional[str] = None,
    include_banned: bool = False,
    allow_aliases: bool = True,
) -> dict[str, Any]:
    if max_age is not None:
        updated_since = (datetime.now(UTC) - timedelta(days=max_age)).isoformat()

    tag_mode = (tags_mode or "or").lower()
    if tag_mode not in {"or", "and"}:
        raise HTTPException(status_code=400, detail="tags_mode must be 'or' or 'and'")

    if allow_aliases:
        source_values = set(_normalize_list(source) + _normalize_list(sources))
        type_values = set(_normalize_list(type) + _normalize_list(types))
    else:
        if _normalize_list(sources):
            raise HTTPException(
                status_code=400,
                detail="Use repeated 'source' parameters; 'sources' is not supported",
            )
        if _normalize_list(types):
            raise HTTPException(
                status_code=400,
                detail="Use repeated 'type' parameters; 'types' is not supported",
            )
        source_values = set(_normalize_list(source))
        type_values = set(_normalize_list(type))

    source_values = set(_canonicalize_sources(db, list(source_values)))
    tag_values = _normalize_list(tags)

    if include_banned:
        if not current_user or current_user.get("role") not in {"admin", "moderator"}:
            raise HTTPException(status_code=403, detail="Moderator or admin role required to view banned products")

    return {
        "source_values": source_values,
        "type_values": type_values,
        "tag_values": tag_values,
        "tag_mode": tag_mode,
        "min_rating": min_rating,
        "updated_since": updated_since,
        "search": search,
        "created_by": created_by,
        "include_banned": include_banned,
    }


def _apply_product_filters(query, db, filters: dict[str, Any]):
    source_values = filters["source_values"]
    type_values = filters["type_values"]
    tag_values = filters["tag_values"]

    if source_values:
        query = query.in_("source", list(source_values))

    if type_values:
        query = query.in_("type", list(type_values))

    if tag_values:
        product_ids_with_tags = get_product_ids_for_tags(db, tag_values, filters["tag_mode"])
        if not product_ids_with_tags:
            return None
        query = query.in_("id", list(product_ids_with_tags))

    if filters["search"]:
        query = query.ilike("name", f"%{filters['search']}%")

    if filters["created_by"]:
        query = query.eq("created_by", filters["created_by"])

    if not filters["include_banned"]:
        query = query.eq("banned", False)

    if filters["updated_since"] is not None:
        query = query.gte("source_last_updated", filters["updated_since"])

    if filters["min_rating"] is not None:
        min_rating = filters["min_rating"]
        # Include products where either computed rating or source rating meets threshold.
        query = query.or_(f"computed_rating.gte.{min_rating},source_rating.gte.{min_rating}")

    return query


def _fetch_filtered_product_ids(db, filters: dict[str, Any]) -> list[str]:
    query = _apply_product_filters(db.table("products").select("id"), db, filters)
    if query is None:
        return []

    if getattr(db, "backend", None) != "supabase":
        resp = query.execute()
        return [row["id"] for row in (resp.data or []) if row.get("id")]

    ids: list[str] = []
    page_size = 500
    offset = 0
    while True:
        resp = query.range(offset, offset + page_size - 1).execute()
        rows = resp.data or []
        if not rows:
            break
        ids.extend([row["id"] for row in rows if row.get("id")])
        if len(rows) < page_size:
            break
        offset += page_size
    return ids


def _without_min_rating(filters: dict[str, Any]) -> dict[str, Any]:
    base_filters = dict(filters)
    base_filters["min_rating"] = None
    return base_filters


@router.get("/sources")
async def get_product_sources(
    response: Response,
    db = Depends(get_db),
):
    """Get all unique source values from products table with product counts.
    
    Returns a list of sources with their product counts for filter UI.
    Uses supported_sources as the canonical list and unions with actual
    source values found in products. All values are camelcased to canonical
    names when available; otherwise title-cased.
    """
    try:
        # Canonical list and mapping from supported_sources
        sources_resp = db.table("supported_sources").select("name").execute()
        canonical_list = [
            row["name"].strip()
            for row in (sources_resp.data or [])
            if row.get("name") and row.get("name").strip()
        ]
        canonical_set = set(canonical_list)
        name_map = {n.lower(): n for n in canonical_list}

        # Count products by source using SQL aggregation
        source_counts: dict[str, int] = {}
        try:
            # Use RPC function for aggregation (faster than fetching all rows)
            rpc_resp = db.rpc('get_product_source_counts').execute()
            for row in (rpc_resp.data or []):
                raw_source = str(row.get("source", "")).strip()
                count = int(row.get("count", 0))
                if raw_source:
                    # Canonicalize to supported_sources name
                    canonical_source = name_map.get(raw_source.lower(), raw_source.title())
                    source_counts[canonical_source] = source_counts.get(canonical_source, 0) + count
        except Exception as e:
            # Fallback to manual aggregation if RPC not available
            logger = logging.getLogger(__name__)
            logger.error(f"RPC not available, using fallback: {e}")
            page_size = 1000
            offset = 0
            while True:
                resp = db.table("products").select("source").range(offset, offset + page_size - 1).execute()
                rows = resp.data or []
                if not rows:
                    break
                for row in rows:
                    s = row.get("source")
                    if s and str(s).strip():
                        raw_source = str(s).strip()
                        canonical_source = name_map.get(raw_source.lower(), raw_source.title())
                        source_counts[canonical_source] = source_counts.get(canonical_source, 0) + 1
                if len(rows) < page_size:
                    break
                offset += page_size

        # Build result list with all canonical sources (even if count is 0)
        result = []
        for source in canonical_set:
            result.append({
                "name": source,
                "count": source_counts.get(source, 0)
            })
        
        # Add any non-canonical sources that have products
        for source, count in source_counts.items():
            if source not in canonical_set:
                result.append({
                    "name": source,
                    "count": count
                })
        
        # Sort by name
        result.sort(key=lambda x: x["name"])
        return {"sources": result}
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Exception: {e}")
        return {"sources": []}


def get_product_ids_for_tags(db, tag_names: list[str], mode: str = "or") -> set[str]:
    """Return product IDs that match provided tag names using OR/AND semantics."""
    if not tag_names:
        return set()
    tag_rows = db.table("tags").select("id,name").in_("name", tag_names).execute()
    tag_map = {row["name"]: row["id"] for row in (tag_rows.data or []) if row.get("id") and row.get("name")}
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


def _safe_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _compute_display_rating(user_average: Optional[float], source_rating: Optional[float]) -> Optional[float]:
    if user_average is not None and source_rating is not None:
        return (user_average + source_rating) / 2
    if user_average is not None:
        return user_average
    if source_rating is not None:
        return source_rating
    return None


def build_display_rating_map(db, products: list[dict]) -> dict[str, dict]:
    """Compute display ratings and counts keyed by product ID."""
    product_ids = [p.get("id") for p in products if p.get("id")]
    if not product_ids:
        return {}

    # Fetch ratings for all products - with proper indexes this is fast even for large batches
    # PostgREST has a limit on URL length, so we still chunk for safety but use larger chunks
    ratings_rows: list[dict] = []
    chunk_size = 500  # Increased from 200 since we now have indexes
    for i in range(0, len(product_ids), chunk_size):
        chunk = product_ids[i:i + chunk_size]
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


def rating_meets_threshold(product: dict, ratings_map: dict[str, dict], min_rating: float) -> bool:
    rating_info = ratings_map.get(product.get("id"), {})
    display_rating = rating_info.get("display_rating")
    if display_rating is None:
        return False
    return display_rating >= min_rating


def attach_rating_fields(db, product: dict, ratings_map: Optional[dict[str, dict]] = None) -> dict:
    """Attach average, count, and display rating to a single product record."""
    # Prefer computed rating, but fall back to source rating when computed is unavailable.
    computed = _safe_float(product.get("computed_rating"))
    source = _safe_float(product.get("source_rating"))
    product["display_rating"] = computed if computed is not None else source
    
    # Only fetch detailed breakdown if needed
    if ratings_map is None and product.get("computed_rating") is not None:
        # Fetch rating details for this one product
        ratings_map = build_display_rating_map(db, [product])
    
    if ratings_map:
        rating_info = ratings_map.get(product.get("id"), {})
        product["average_rating"] = rating_info.get("average_rating")
        product["rating_count"] = rating_info.get("rating_count", 0)
    else:
        product["average_rating"] = None
        product["rating_count"] = 0
    
    return product


@router.get("/types")
async def get_product_types(
    response: Response,
    db = Depends(get_db),
):
    """Get all unique type values from products table.
    
    Returns a sorted list of distinct types for filter UI.
    Uses valid_categories as the canonical list so options stay stable
    regardless of current search filters.
    """
    try:
        # Canonical list from valid_categories
        categories_resp = db.table("valid_categories").select("category").execute()
        canonical_types = {
            row["category"].strip()
            for row in (categories_resp.data or [])
            if row.get("category") and row.get("category").strip()
        }

        # Distinct types present in products
        product_types: set[str] = set()
        try:
            # Try RPC function for better performance
            rpc_resp = db.rpc('get_product_types').execute()
            product_types = {
                str(row.get("type")).strip()
                for row in (rpc_resp.data or [])
                if row.get("type") and str(row.get("type")).strip()
            }
        except Exception:
            # Fallback to distinct query
            try:
                resp = db.table("products").select("type", distinct=True).execute()
                product_types = {
                    str(row.get("type")).strip()
                    for row in (resp.data or [])
                    if row.get("type") and str(row.get("type")).strip()
                }
            except TypeError:
                # Final fallback: paginate (slow but works)
                page_size = 1000
                offset = 0
                while True:
                    resp = db.table("products").select("type").range(offset, offset + page_size - 1).execute()
                    rows = resp.data or []
                    if not rows:
                        break
                    for row in rows:
                        t = row.get("type")
                        if t and str(t).strip():
                            product_types.add(str(t).strip())
                    if len(rows) < page_size:
                        break
                    offset += page_size

        # Combine canonical list and discovered product types
        combined = canonical_types.union(product_types)
        payload = sorted(combined)
        return {"types": payload}
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Exception: {e}")
        return {"types": []}


@router.get("/tags")
async def get_tags(
    response: Response,
    source: Optional[list[str]] = Query(None, alias="source", description="Filter tags by product source"),
    sources: Optional[list[str]] = Query(None, description="Filter tags by product source"),
    type: Optional[list[str]] = Query(None, alias="type", description="Filter tags by product type"),
    types: Optional[list[str]] = Query(None, description="Filter tags by product type"),
    search: Optional[str] = Query(None, description="Case-insensitive substring filter on product name"),
    updated_since: Optional[str] = Query(None, description="Filter products updated at source since this date (ISO format)"),
    created_by: Optional[str] = None,
    include_banned: bool = Query(False, description="Include banned products (admin/mod only)"),
    tag_search: Optional[str] = Query(None, description="Case-insensitive substring filter on tag name"),
    limit: Optional[int] = Query(None, le=1000, description="Optional cap; omit to return all tags"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db = Depends(get_db),
):
    """Get tag names for products matching the provided filters.

    - Uses the same filters as /products (source/type/search/created_by).
    - Returns tag names alphabetically.
    - Optional tag_search filters tag names.
    - Optional limit (up to 1000); omit limit to return all.
    - include_banned: set to true to include banned products (requires admin/moderator role).
    """
    try:
        # Try optimized RPC function first
        source_values = set(_normalize_list(source) + _normalize_list(sources))
        source_values = set(_canonicalize_sources(db, list(source_values)))
        type_values = set(_normalize_list(type) + _normalize_list(types))
        
        try:
            params = {
                "p_sources": list(source_values) if source_values else None,
                "p_types": list(type_values) if type_values else None,
                "p_name_search": search,
                "p_tag_search": tag_search,
                "p_limit": limit,
                "p_created_by": created_by,
                "p_updated_since": updated_since,
                "p_include_banned": include_banned
            }
            rpc_resp = db.rpc('get_product_tags_filtered', params).execute()
            names = [row.get("tag_name") for row in (rpc_resp.data or []) if row.get("tag_name")]
            return {"tags": names}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"RPC not available, using fallback: {e}")
            # Fallback to original implementation
            pass

        # First, find product_ids matching filters (consistent with /products)
        product_query = db.table("products").select("id")

        if source_values:
            product_query = product_query.in_("source", list(source_values))

        if type_values:
            product_query = product_query.in_("type", list(type_values))

        if search:
            product_query = product_query.ilike("name", f"%{search}%")

        if created_by:
            product_query = product_query.eq("created_by", created_by)
        
        if updated_since is not None:
            product_query = product_query.gte("source_last_updated", updated_since)

        # Handle banned products
        if include_banned:
            if not current_user or current_user.get("role") not in {"admin", "moderator"}:
                raise HTTPException(status_code=403, detail="Moderator or admin role required to view banned products")
        else:
            product_query = product_query.eq("banned", False)

        product_resp = product_query.execute()
        product_ids = [row["id"] for row in (product_resp.data or [])]

        if not product_ids:
            return {"tags": []}

        # Fetch tag_ids for these products in chunks to avoid URL length limits
        # PostgreSQL/PostgREST has limits on query string length for .in_() filters
        tag_ids_set = set()
        chunk_size = 500
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i:i + chunk_size]
            pt_resp = db.table("product_tags").select("tag_id").in_("product_id", chunk).execute()
            for row in (pt_resp.data or []):
                if row.get("tag_id"):
                    tag_ids_set.add(row["tag_id"])

        tag_ids = list(tag_ids_set)
        if not tag_ids:
            return {"tags": []}

        # Fetch tag names, optionally filtered by tag name search
        # Also chunk the tag_ids query to avoid URL length limits
        names_set = set()
        for i in range(0, len(tag_ids), chunk_size):
            chunk = tag_ids[i:i + chunk_size]
            tag_query = db.table("tags").select("name").in_("id", chunk)
            if tag_search:
                tag_query = tag_query.ilike("name", f"%{tag_search}%")
            tags_resp = tag_query.execute()
            for row in (tags_resp.data or []):
                if row.get("name"):
                    names_set.add(row["name"])

        names = sorted(names_set)
        if limit is not None:
            names = names[:max(limit, 0)]

        return {"tags": names}
    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Tag Fetch] Failed: {e}")
        return {"tags": []}


@router.get("", response_model=list[ProductResponse])
async def get_products(
    source: Optional[list[str]] = Query(None, alias="source", description="Comma-separated or repeated source values"),
    sources: Optional[list[str]] = Query(None, description="Comma-separated or repeated source values"),
    type: Optional[list[str]] = Query(None, alias="type", description="Comma-separated or repeated type values"),
    types: Optional[list[str]] = Query(None, description="Comma-separated or repeated type values"),
    tags: Optional[list[str]] = Query(None, alias="tags", description="Filter products that have any of these tag names"),
    tags_mode: str = Query("or", pattern="^(?i)(or|and)$", description="Tag filter mode: or (default) or and"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum display rating (user or source)"),
    updated_since: Optional[str] = Query(None, description="Filter products updated at source since this date (ISO format)"),
    max_age: Optional[int] = Query(None, description="Filter products updated in the last N days"),
    search: Optional[str] = None,
    created_by: Optional[str] = None,
    include_banned: bool = Query(False, description="Include banned products (admin/mod only)"),
    include_ratings: bool = Query(False, description="Include rating data (average_rating, rating_count, display_rating). Set to true only when displaying ratings."),
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|rating)$", description="Sort by: created_at (default), updated_at, or rating"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order: desc (default) or asc"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db = Depends(get_db),
):
    """Get all products with optional filters.
    
    Loads ownership and tag data via relationship tables to avoid JSON array storage.
    Returns denormalized response with editor_ids and tags attached to each product.
    Query supports filtering by source platform, type, text search, and creator.
    """
    filters = _prepare_product_filters(
        db,
        current_user,
        source=source,
        sources=sources,
        type=type,
        types=types,
        tags=tags,
        tags_mode=tags_mode,
        min_rating=min_rating,
        updated_since=updated_since,
        max_age=max_age,
        search=search,
        created_by=created_by,
        include_banned=include_banned,
        allow_aliases=True,
    )

    query = _apply_product_filters(db.table("products").select("*"), db, filters)
    if query is None:
        return []

    # Apply ordering based on sort_by parameter
    # Now all sorting happens in SQL thanks to computed_rating column
    if sort_by == "rating":
        sort_field = "computed_rating"
    elif sort_by == "updated_at":
        sort_field = "source_last_updated"
    else:
        sort_field = "created_at"
    
    is_desc = (sort_order == "desc")
    # For rating sort, put NULL values last regardless of sort direction
    if sort_by == "rating":
        query = query.order(sort_field, desc=is_desc, nullsfirst=False)
        # Apply recency as a secondary sort key so ties are broken by most recent first
        query = query.order("created_at", desc=True)
    else:
        query = query.order(sort_field, desc=is_desc)
    
    # Apply pagination in SQL
    query = query.range(offset, offset + limit - 1)
    
    response = query.execute()

    # Collect product IDs
    products = response.data or []
    
    # Fetch ratings only when explicitly requested for display
    ratings_map = {}
    if include_ratings:
        ratings_map = build_display_rating_map(db, products)

    product_ids = [p["id"] for p in products]

    # Load owners for each product
    owners_by_product: dict[str, list[str]] = {}
    if product_ids:
        owners_rows = db.table("product_editors").select("product_id, user_id").in_("product_id", product_ids).execute()
        for row in owners_rows.data or []:
            pid = row.get("product_id")
            uid = row.get("user_id")
            if pid and uid:
                owners_by_product.setdefault(pid, []).append(uid)

    # Load tags via relationship tables
    tags_by_product: dict[str, list[str]] = {}
    if product_ids:
        pt_rows = get_product_tag_rows(db, product_ids)
        tag_ids = list({row["tag_id"] for row in pt_rows}) if pt_rows else []
        tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
        for row in pt_rows:
            pid = row["product_id"]
            tname = tags_map.get(row["tag_id"]) if row["tag_id"] in tags_map else None
            if tname:
                tags_by_product.setdefault(pid, []).append(tname)

    # Fetch supported_sources map once (not once per product!)
    source_name_map = _get_supported_source_name_map(db)

    # Normalize fields and attach tags
    normalized = []
    for item in products:
        # Add top-level stars derived from source_rating_count
        item["stars"] = item.get("source_rating_count") or 0
        
        # Prefer computed rating, but fall back to source rating.
        computed = _safe_float(item.get("computed_rating"))
        source = _safe_float(item.get("source_rating"))
        item["display_rating"] = computed if computed is not None else source
        
        # Only fetch detailed rating breakdown if explicitly requested
        if ratings_map:
            rating_info = ratings_map.get(item["id"], {})
            item["average_rating"] = rating_info.get("average_rating")
            item["rating_count"] = rating_info.get("rating_count", 0)
        else:
            # Set defaults when detailed ratings not fetched
            item["average_rating"] = None
            item["rating_count"] = 0
        
        # Normalize fields for API clients
        if "image" in item:
            item["image_url"] = item.get("image")
        if "url" in item:
            item["source_url"] = item.get("url")
        # Ensure canonical source display names using supported_sources (use pre-fetched map)
        if "source" in item and item.get("source"):
            source_key = str(item.get("source")).strip().lower()
            item["source"] = source_name_map.get(source_key, item.get("source"))
        item["tags"] = tags_by_product.get(item["id"], [])
        item["editor_ids"] = owners_by_product.get(item["id"], [])
        normalized.append(item)

    return normalized


@router.get("/count")
async def count_products(
    source: Optional[list[str]] = Query(None, alias="source", description="Comma-separated or repeated source values"),
    sources: Optional[list[str]] = Query(None, description="Comma-separated or repeated source values"),
    type: Optional[list[str]] = Query(None, alias="type", description="Comma-separated or repeated type values"),
    types: Optional[list[str]] = Query(None, description="Comma-separated or repeated type values"),
    tags: Optional[list[str]] = Query(None, alias="tags", description="Filter products that have any of these tag names"),
    tags_mode: str = Query("or", pattern="^(?i)(or|and)$", description="Tag filter mode: or (default) or and"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum display rating (user or source)"),
    updated_since: Optional[str] = Query(None, description="Filter products updated at source since this date (ISO format)"),
    max_age: Optional[int] = Query(None, description="Filter products updated in the last N days"),
    search: Optional[str] = None,
    created_by: Optional[str] = None,
    include_banned: bool = Query(False, description="Include banned products (admin/mod only)"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db = Depends(get_db),
):
    """Get total count of products matching filters (for pagination UI).
    
    Returns {count: int} to help frontend paginate through all matching products.
    Applies same filters as /api/products but returns only the count.
    """
    filters = _prepare_product_filters(
        db,
        current_user,
        source=source,
        sources=sources,
        type=type,
        types=types,
        tags=tags,
        tags_mode=tags_mode,
        min_rating=min_rating,
        updated_since=updated_since,
        max_age=max_age,
        search=search,
        created_by=created_by,
        include_banned=include_banned,
        allow_aliases=True,
    )

    total = None
    try:
        count_query = _apply_product_filters(db.table("products").select("id", count="exact"), db, filters)
        if count_query is None:
            return {"count": 0}
        count_resp = count_query.execute()
        if getattr(count_resp, "count", None) is not None:
            total = count_resp.count
        else:
            total = len(count_resp.data or [])
    except TypeError:
        count_query = _apply_product_filters(db.table("products").select("id"), db, filters)
        if count_query is None:
            return {"count": 0}
        count_resp = count_query.execute()
        total = len(count_resp.data or [])

    return {"count": total}


@router.get("/exists")
async def product_exists(
    source_url: str,
    db = Depends(get_db),
):
    """Check if a product exists by its source URL.
    
    Used by scrapers and frontend to avoid duplicate submissions.
    Returns {exists: bool, product: ProductResponse | null}.
    """
    response = db.table("products").select("*").eq("url", source_url).limit(1).execute()
    if response.data:
        item = response.data[0]
        if item.get("banned"):
            normalized = _normalize_product(item, db)
            normalized.pop("url", None)
            return {"exists": True, "product": normalized, "banned": True}
        # Normalize fields
        item["tags"] = item.get("tags") or []
        item["stars"] = item.get("source_rating_count") or 0
        if "image" in item:
            item["image_url"] = item.get("image")
        if "url" in item:
            item["source_url"] = item.get("url")
            item.pop("url", None)
        # Add editor_ids from relationship table
        owners_response = db.table("product_editors").select("user_id").eq("product_id", item["id"]).execute()
        item["editor_ids"] = [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
        attach_rating_fields(db, item)
        return {"exists": True, "product": item}
    return {"exists": False}


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db = Depends(get_db),
):
    """Get a single product by ID"""
    result = _get_product_by_identifier(db, product_id)

    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    product_id = result["id"]
    # Attach editor_ids
    owners_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
    result["editor_ids"] = [row["user_id"] for row in owners_response.data] if owners_response.data else []
    # Attach tags via relationship
    pt_rows = get_product_tag_rows(db, [product_id])
    tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
    tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
    result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    # Add top-level stars derived from source_rating_count
    result["stars"] = result.get("source_rating_count") or 0
    # Normalize fields for API clients
    if "image" in result:
        result["image_url"] = result.get("image")
    if "url" in result:
        result["source_url"] = result.get("url")
    attach_rating_fields(db, result)
    
    return result


@router.get("/slug/{slug}", response_model=ProductResponse)
async def get_product_by_slug(
    slug: str,
    db = Depends(get_db),
):
    """Get a single product by slug (human-readable ID)"""
    response = db.table("products").select("*").eq("slug", slug).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")

    result = response.data[0]
    owners_response = db.table("product_editors").select("user_id").eq("product_id", result["id"]).execute()
    result["editor_ids"] = [row["user_id"] for row in owners_response.data] if owners_response.data else []
    pt_rows = get_product_tag_rows(db, [result["id"]])
    tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
    tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
    result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    result["stars"] = result.get("source_rating_count") or 0
    if "image" in result:
        result["image_url"] = result.get("image")
    if "url" in result:
        result["source_url"] = result.get("url")
    attach_rating_fields(db, result)

    return result


@router.get("/{slug}/collections")
async def get_product_collections(
    slug: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db = Depends(get_db),
):
    """Get all collections that contain this product.
    
    Returns public collections for unauthenticated users.
    Returns public + user's private collections for authenticated users.
    """
    # Get product by slug
    product_resp = db.table("products").select("id").eq("slug", slug).execute()
    if not product_resp.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product_id = product_resp.data[0]["id"]
    
    # Get collection IDs from junction table
    junction_resp = db.table("collection_products").select("collection_id").eq("product_id", product_id).execute()
    collection_ids = [row["collection_id"] for row in (junction_resp.data or [])]
    
    if not collection_ids:
        return []
    
    # Fetch collections
    collections_resp = db.table("collections").select("*").in_("id", collection_ids).execute()
    collections = collections_resp.data or []
    
    # Filter based on authentication
    user_id = current_user.get("id") if current_user else None
    filtered_collections = [
        c for c in collections
        if c.get("is_public") or (user_id and c.get("user_id") == user_id)
    ]
    
    # Populate product_ids and product_slugs for each collection
    for collection in filtered_collections:
        products_resp = db.table("collection_products").select("product_id, products(slug)").eq("collection_id", collection["id"]).order("position").execute()
        collection["product_ids"] = [p["product_id"] for p in (products_resp.data or [])]
        collection["product_slugs"] = [p["products"]["slug"] if p.get("products") else None for p in (products_resp.data or [])]
    
    return filtered_collections


def _normalize_product(product: dict, db) -> dict:
    """Attach derived fields (owners, tags, stars, url/image aliases)."""
    pid = product.get("id")
    owners_response = db.table("product_editors").select("user_id").eq("product_id", pid).execute()
    product["editor_ids"] = [row["user_id"] for row in owners_response.data] if owners_response.data else []

    pt_rows = get_product_tag_rows(db, [pid])
    tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
    tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
    product["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]

    product["stars"] = product.get("source_rating_count") or 0
    if "image" in product:
        product["image_url"] = product.get("image")
    if "image_alt" in product:
        product["image_alt"] = product.get("image_alt")
    if "url" in product:
        product["source_url"] = product.get("url")
    attach_rating_fields(db, product)
    return product



@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    product: ProductCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Create a new product (authenticated users only).
    
    Validates product URL against supported sources and auto-assigns source name.
    Supports upsert by URL: if product with same URL exists, updates it instead.
    Automatically adds creator as product editor/owner in product_editors table.
    Security: Requires valid auth token; all users can create products.
    """
    # Get list of supported sources
    sources_response = db.table("supported_sources").select("domain, name").execute()
    supported_sources = sources_response.data or []
    
    # Extract domain from URL and validate against supported sources
    source_url = str(product.source_url) if product.source_url else None
    determined_source = None
    
    if not source_url:
        raise HTTPException(status_code=400, detail="Product URL is required")
    
    domain = extract_domain(source_url)
    if domain:
        determined_source = find_source_for_domain(domain, supported_sources)
    
    # If URL provided but domain not in supported list, reject the submission
    if not determined_source:
        raise HTTPException(
            status_code=400,
            detail=f"URL domain is not supported. Supported domains are: {', '.join([s['domain'] for s in supported_sources])}"
        )
    
    # Map Pydantic model fields to database columns (use attributes to avoid alias issues)
    db_data = {
        "name": product.name,
        "description": product.description,
        "url": source_url,
        "image": str(product.image_url) if product.image_url else None,
        "image_alt": product.image_alt,
        "source": determined_source,  # Auto-assigned, not from user input
        "type": product.type or "Other",
        "external_id": product.external_id,
        "created_by": current_user["id"]
    }
    
    # Enrich metadata from source scrapers (best-effort)
    await _enrich_manual_product_metadata(db, determined_source, source_url, product, db_data)

    # Upsert behavior: If URL provided and product exists, update instead of creating.
    # This prevents duplicate products from scrapers while allowing manual updates.
    if db_data.get("url"):
        existing = db.table("products").select("*").eq("url", db_data["url"]).limit(1).execute()
        if existing.data:
            existing_product = existing.data[0]
            if existing_product.get("banned"):
                raise HTTPException(status_code=403, detail="Product is banned and cannot be resubmitted")
            # Build update data, excluding immutable fields like created_by
            update_data = {k: v for k, v in db_data.items() if k in {
                "name", "description", "url", "image", "image_alt", "source", "type", "external_id", "source_last_updated"
            } and v is not None}

            # Ensure legacy rows get a slug assigned
            if not existing_product.get("slug"):
                update_data["slug"] = generate_id_with_uniqueness_check(product.name, db, "products", column="slug")
            updated = db.table("products").update(update_data).eq("id", existing_product["id"]).execute()
            result = updated.data[0] if updated.data else existing_product
            product_id = result["id"]
            # Normalize fields for API response
            result["image_url"] = result.get("image")
            result["external_id"] = result.get("external_id")
            
            # Add current user as owner if not already one
            existing_owner = db.table("product_editors").select("*").eq("product_id", product_id).eq("user_id", current_user["id"]).execute()
            if not existing_owner.data:
                import uuid
                owner_data = {
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "user_id": current_user["id"]
                }
                db.table("product_editors").insert(owner_data).execute()
            
            # Add editor_ids to response
            owners_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
            result["editor_ids"] = [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
            
            # Update tag relationships if provided
            if product.tags is not None:
                try:
                    set_product_tags(db, result["id"], product.tags)
                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"[Tags] Failed to set tags for duplicate product {result['id']}: {e}")
                    result["tags"] = []
            else:
                # Attach tags for response
                try:
                    pt_rows = get_product_tag_rows(db, [result["id"]])
                    tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
                    tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
                    result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"[Tags] Failed to fetch tags for duplicate product {result['id']}: {e}")
                    result["tags"] = []
            return result

    # Generate human-readable slug for URLs (unique per product)
    slug = generate_id_with_uniqueness_check(product.name, db, "products", column="slug")

    # Add the generated slug to the insert data
    db_insert = {k: v for k, v in db_data.items() if v is not None}
    db_insert["slug"] = slug
    response = db.table("products").insert(db_insert).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create product")

    # Map database response back to API response format
    result = response.data[0]
    product_id = result["id"]
    result["image_url"] = result.get("image")
    result["external_id"] = result.get("external_id")
    
    # Add creator as product manager
    import uuid
    owner_data = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "user_id": current_user["id"]
    }
    db.table("product_editors").insert(owner_data).execute()
    
    # Add editor_ids to response
    owners_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
    result["editor_ids"] = [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
    
    # Create tag relationships if provided
    if product.tags:
        try:
            set_product_tags(db, result["id"], product.tags)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[Tags] Failed to create tags for product {result['id']}: {e}")
            result["tags"] = []
            return result
    
    # Attach tags for response
    try:
        pt_rows = get_product_tag_rows(db, [result["id"]])
        tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
        tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
        result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Tags] Failed to fetch tags for product {result['id']}: {e}")
        result["tags"] = []

    return result


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product: ProductUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Update a product (creator/editor or admin only).
    
    Security: Enforces ownership via product_editors table OR admin role.
    Prevents unauthorized users from modifying products they don't manage.
    """
    product_row = _get_product_by_identifier(db, product_id)
    if not product_row:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product_row.get("banned"):
        raise HTTPException(status_code=403, detail="Product is banned and cannot be edited")
    product_id = product_row["id"]
    # Authorization check
    is_creator = product_row.get("created_by") == current_user["id"]
    role = current_user.get("role")
    is_admin_or_moderator = role in ("admin", "moderator")
    
    # Check if user is in product_editors if not creator/admin/moderator
    is_editor = False
    if not is_creator and not is_admin_or_moderator:
        from services.database import db_adapter
        editors_check = db_adapter.supabase.table("product_editors").select("user_id").eq("product_id", product_id).eq("user_id", current_user["id"]).execute()
        is_editor = bool(editors_check.data)
    
    # Require at least one authorization path
    if not (is_creator or is_admin_or_moderator or is_editor):
        raise HTTPException(status_code=403, detail="Not authorized to update this product")
    
    # Map API fields to database columns (use attributes to avoid alias issues)
    product_data = product.model_dump(exclude_unset=True)
    db_data = {}

    if "name" in product_data:
        db_data["name"] = product_data["name"]
    if "description" in product_data:
        db_data["description"] = product_data["description"]
    if "source_url" in product_data and product.source_url is not None:
        db_data["url"] = str(product.source_url)
    if "image_url" in product_data and product.image_url is not None:
        db_data["image"] = str(product.image_url)
    if "image_alt" in product_data:
        db_data["image_alt"] = product.image_alt
    if "source" in product_data:
        db_data["source"] = _canonicalize_source_value_db(db, product_data["source"]) or product_data["source"]
    if "type" in product_data and product.type is not None:
        db_data["type"] = product.type
    if "external_id" in product_data:
        db_data["external_id"] = product_data["external_id"]
    # Apply basic field updates
    
    if db_data:
        response = db.table("products").update(db_data).eq("id", product_id).execute()
        if not response.data:
            # Likely blocked by RLS or no rows updated
            raise HTTPException(status_code=403, detail="Not authorized to update this product")
    else:
        # No product fields to update, just fetch the current product
        response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Product not found")
    
    # Update tag relationships if requested
    if "tags" in product_data:
        try:
            set_product_tags(db, product_id, product_data["tags"] or [])
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[Tags] Failed to update tags for product {product_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update product tags: {str(e)}")

    # Map database response back to API format
    result = response.data[0]
    result["image_url"] = result.get("image")
    result["external_id"] = result.get("external_id")
    
    # Attach editor_ids
    try:
        owners_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
        result["editor_ids"] = [owner["user_id"] for owner in owners_response.data] if owners_response.data else []
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Editors] Failed to fetch editors for product {product_id}: {e}")
        result["editor_ids"] = []
    
    # Attach tags
    try:
        pt_rows = get_product_tag_rows(db, [product_id])
        tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
        tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
        result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Tags] Failed to fetch tags for product {product_id}: {e}")
        result["tags"] = []
    
    return result


@router.patch("/{product_id}", response_model=ProductResponse)
async def patch_product(
    product_id: str,
    product: ProductUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Partially update a product (manager or admin only)"""
    product_row = _get_product_by_identifier(db, product_id)
    if not product_row:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check authorization: must be creator, product manager, admin, or moderator
    if product_row.get("banned"):
        raise HTTPException(status_code=403, detail="Product is banned and cannot be edited")
    product_id = product_row["id"]
    is_creator = product_row.get("created_by") == current_user["id"]
    role = current_user.get("role")
    is_admin_or_moderator = role in ("admin", "moderator")
    
    # Check if user is in product_editors if not creator/admin/moderator
    is_editor = False
    if not is_creator and not is_admin_or_moderator:
        from services.database import db_adapter
        editors_check = db_adapter.supabase.table("product_editors").select("user_id").eq("product_id", product_id).eq("user_id", current_user["id"]).execute()
        is_editor = bool(editors_check.data)
    
    # Require at least one authorization path
    if not (is_creator or is_admin_or_moderator or is_editor):
        raise HTTPException(status_code=403, detail="Not authorized to update this product")
    
    # Map API fields to database columns
    product_data = product.model_dump(exclude_unset=True)
    db_data = {}

    if "name" in product_data:
        db_data["name"] = product_data["name"]
    if "description" in product_data:
        db_data["description"] = product_data["description"]
    if "source_url" in product_data and product.source_url is not None:
        db_data["url"] = str(product.source_url)
    if "image_url" in product_data and product.image_url is not None:
        db_data["image"] = str(product.image_url)
    if "image_alt" in product_data:
        db_data["image_alt"] = product.image_alt
    if "source" in product_data:
        db_data["source"] = _canonicalize_source_value_db(db, product_data["source"]) or product_data["source"]
    if "type" in product_data and product.type is not None:
        db_data["type"] = product.type
    if "external_id" in product_data:
        db_data["external_id"] = product_data["external_id"]
    if "source_last_updated" in product_data and product.source_last_updated is not None:
        db_data["source_last_updated"] = product.source_last_updated
    
    try:
        # Update the product if there are fields to update (permissions already checked above)
        if db_data:
            response = db.table("products").update(db_data).eq("id", product_id).execute()
            if not response.data:
                # Should not happen since we verified permissions above
                raise HTTPException(status_code=500, detail="Update failed unexpectedly")
            result = response.data[0]
        else:
            # No product fields to update, just fetch the current product
            response = db.table("products").select("*").eq("id", product_id).limit(1).execute()
            if not response.data:
                raise HTTPException(status_code=404, detail="Product not found")
            result = response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Update] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update product: {str(e)}")
    
    # Update tag relationships if requested
    if "tags" in product_data:
        try:
            set_product_tags(db, product_id, product_data["tags"] or [])
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"[Tags] Failed to update tags for product {product_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update product tags: {str(e)}")

    # Map database response back to API format
    result["image_url"] = result.get("image")
    result["external_id"] = result.get("external_id")
    
    # Attach editor_ids
    try:
        editors_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
        result["editor_ids"] = [editor["user_id"] for editor in editors_response.data] if editors_response.data else []
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Editors] Failed to fetch editors for product {product_id}: {e}")
        result["editor_ids"] = []
    
    # Attach tags
    try:
        pt_rows = get_product_tag_rows(db, [product_id])
        tag_ids = [row["tag_id"] for row in pt_rows] if pt_rows else []
        tags_map = get_tags_map(db, tag_ids) if tag_ids else {}
        result["tags"] = [tags_map[tid] for tid in tag_ids if tid in tags_map]
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Tags] Failed to fetch tags for product {product_id}: {e}")
        result["tags"] = []
    
    return result


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Delete a product (admin only)
    
    Note: Most related data (ratings, discussions, product_urls, etc.) will be 
    automatically deleted via CASCADE. We explicitly handle a few tables that 
    might not cascade properly.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not current_user.get("role") == "admin":
        raise HTTPException(
            status_code=403, 
            detail=f"Admin access required. Your current role: {current_user.get('role', 'user')}"
        )
    
    # Check if product exists first; accept either ID or slug for convenience.
    # Avoid UUID parsing errors by only querying id when the input resembles a UUID.
    resolved_id = None
    if _looks_like_uuid(product_id):
        check = db.table("products").select("id").eq("id", product_id).limit(1).execute()
        if check.data:
            resolved_id = check.data[0]["id"]
    if not resolved_id:
        slug_lookup = db.table("products").select("id").eq("slug", product_id).limit(1).execute()
        if not slug_lookup.data:
            raise HTTPException(status_code=404, detail="Product not found")
        resolved_id = slug_lookup.data[0]["id"]
    product_id = resolved_id
    
    # The database schema has ON DELETE CASCADE for most relationships,
    # so they should auto-delete. But we can be explicit for safety.
    # These will cascade: ratings, discussions, product_urls, product_editors, product_tags
    # Just delete the product - CASCADE should handle the rest
    try:
        print(f"[Delete] Deleting product {product_id}")
        db.table("products").delete().eq("id", product_id).execute()
        print(f"[Delete] Success")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Delete] Failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete product: {str(e)}"
        )


@router.post("/bulk-delete", status_code=200)
async def bulk_delete_products(
    source: Optional[list[str]] = Query(None, alias="source", description="Comma-separated or repeated source values"),
    sources: Optional[list[str]] = Query(None, description="Comma-separated or repeated source values"),
    type: Optional[list[str]] = Query(None, alias="type", description="Comma-separated or repeated type values"),
    types: Optional[list[str]] = Query(None, description="Comma-separated or repeated type values"),
    tags: Optional[list[str]] = Query(None, alias="tags", description="Filter products that have any of these tag names"),
    tags_mode: str = Query("or", pattern="^(?i)(or|and)$", description="Tag filter mode: or (default) or and"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum display rating (user or source)"),
    updated_since: Optional[str] = Query(None, description="Filter products updated at source since this date (ISO format)"),
    max_age: Optional[int] = Query(None, description="Filter products updated in the last N days"),
    search: Optional[str] = None,
    created_by: Optional[str] = None,
    include_banned: bool = Query(False, description="Include banned products (admin/mod only)"),
    product_ids: Optional[list[str]] = Query(None, description="Specific product IDs to delete"),
    payload: Optional[BulkDeleteRequest] = Body(None, description="Optional JSON body mirroring query params"),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Bulk delete products (admin only).
    
    Deletes the server-side search result set for the supplied filters.
    Supports the same core filters as GET /api/products plus legacy product_ids.
    
    Returns count of deleted products.
    
    Note: Related data (ratings, discussions, etc.) will be automatically 
    deleted via database CASCADE constraints.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not current_user.get("role") == "admin":
        raise HTTPException(
            status_code=403,
            detail=f"Admin access required. Your current role: {current_user.get('role', 'user')}"
        )
    
    # Accept values from query params or JSON body for flexibility with callers
    normalized_product_ids = _normalize_list(product_ids) + _normalize_list(payload.product_ids if payload else None)
    filters = _prepare_product_filters(
        db,
        current_user,
        source=_normalize_list(source) + _normalize_list(payload.source if payload else None),
        sources=_normalize_list(sources) + _normalize_list(payload.sources if payload else None),
        type=_normalize_list(type) + _normalize_list(payload.type if payload else None),
        types=_normalize_list(types) + _normalize_list(payload.types if payload else None),
        tags=_normalize_list(tags) + _normalize_list(payload.tags if payload else None),
        tags_mode=(
            payload.tags_mode
            if payload and "tags_mode" in payload.model_fields_set
            else tags_mode
        ),
        min_rating=payload.min_rating if payload and payload.min_rating is not None else min_rating,
        updated_since=payload.updated_since if payload and payload.updated_since is not None else updated_since,
        max_age=payload.max_age if payload and payload.max_age is not None else max_age,
        search=payload.search if payload and payload.search is not None else search,
        created_by=payload.created_by if payload and payload.created_by is not None else created_by,
        include_banned=(
            payload.include_banned
            if payload and "include_banned" in payload.model_fields_set
            else include_banned
        ),
        allow_aliases=False,
    )

    has_search_filters = any([
        filters["source_values"],
        filters["type_values"],
        filters["tag_values"],
        filters["search"],
        filters["created_by"],
        filters["updated_since"] is not None,
        filters["min_rating"] is not None,
    ])

    if not has_search_filters and not normalized_product_ids:
        raise HTTPException(
            status_code=400,
            detail="Must provide either search filters or 'product_ids' parameter (query or JSON body)"
        )
    
    try:
        ids_to_delete: list[str] = []
        if has_search_filters:
            ids_to_delete.extend(_fetch_filtered_product_ids(db, filters))
        if normalized_product_ids:
            ids_to_delete.extend(normalized_product_ids)
        ids_to_delete = list(dict.fromkeys(ids_to_delete))

        if not ids_to_delete:
            return {"deleted_count": 0, "message": "No products found matching criteria"}

        print(f"[Bulk Delete] About to delete {len(ids_to_delete)} products: {ids_to_delete[:5]}...")
        print(f"[Bulk Delete] Backend type: supabase")

        async def _delete_supabase(ids: list[str]) -> int:
            # Use REST endpoint with Prefer:return=minimal to avoid JSON serialization errors
            headers = {
                "apikey": settings.SUPABASE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_KEY}",
                "Prefer": "return=minimal",
            }
            deleted = 0
            chunk_size = 200
            async with httpx.AsyncClient(base_url=settings.SUPABASE_URL, timeout=30) as client:
                for i in range(0, len(ids), chunk_size):
                    chunk = ids[i:i + chunk_size]
                    params = {"id": f"in.({','.join(chunk)})"}
                    resp = await client.delete("/rest/v1/products", params=params, headers=headers)
                    if resp.status_code not in (200, 204):
                        print(
                            f"[Bulk Delete] Supabase chunk delete failed: status={resp.status_code}, body={resp.text[:400]}"
                        )
                        raise HTTPException(status_code=500, detail="Failed to delete products in Supabase")
                    deleted += len(chunk)
            return deleted

        await _delete_supabase(ids_to_delete)

        print(f"[Bulk Delete] Delete completed for {len(ids_to_delete)} IDs")

        return {
            "deleted_count": len(ids_to_delete),
            "message": f"Successfully deleted {len(ids_to_delete)} product(s)",
            "source": next(iter(filters["source_values"])) if len(filters["source_values"]) == 1 else None
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"[Bulk Delete] Failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete products: {str(e)}"
        )


def _ensure_moderator_or_admin(current_user: dict):
    if not current_user or current_user.get("role") not in {"admin", "moderator"}:
        raise HTTPException(status_code=403, detail="Moderator or admin access required")


@router.post("/{product_slug}/ban", response_model=ProductResponse)
async def ban_product(
    product_slug: str,
    payload: dict = None,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Ban a product from scraper updates (moderator/admin) by slug."""
    _ensure_moderator_or_admin(current_user)

    # Resolve slug to product ID; fall back to ID if provided
    product_response = db.table("products").select("id").eq("slug", product_slug).limit(1).execute()
    if not product_response.data and _looks_like_uuid(product_slug):
        product_response = db.table("products").select("id").eq("id", product_slug).limit(1).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    product_id = product_response.data[0]["id"]

    reason = None
    if payload:
        reason = payload.get("reason")

    update_data = {
        "banned": True,
        "banned_reason": reason,
        "banned_by": current_user.get("id"),
        "banned_at": datetime.now(UTC).isoformat()
    }

    updated = db.table("products").update(update_data).eq("id", product_id).execute()
    if not updated.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product = updated.data[0]
    return _normalize_product(product, db)


@router.post("/{product_slug}/unban", response_model=ProductResponse)
async def unban_product(
    product_slug: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_db),
):
    """Remove ban from a product (moderator/admin) by slug."""
    _ensure_moderator_or_admin(current_user)

    # Resolve slug to product ID; fall back to ID if provided
    product_response = db.table("products").select("id").eq("slug", product_slug).limit(1).execute()
    if not product_response.data and _looks_like_uuid(product_slug):
        product_response = db.table("products").select("id").eq("id", product_slug).limit(1).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    product_id = product_response.data[0]["id"]

    updated = db.table("products").update({
        "banned": False,
        "banned_reason": None,
        "banned_by": None,
        "banned_at": None
    }).eq("id", product_id).execute()

    if not updated.data:
        raise HTTPException(status_code=404, detail="Product not found")

    product = updated.data[0]
    return _normalize_product(product, db)


@router.get("/{product_id}/owners")
async def get_product_editors(
    product_id: str,
    db = Depends(get_db),
):
    """Get all editors of a product"""
    # First check if product exists
    product_response = db.table("products").select("id").eq("id", product_id).execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get all editor relationships
    editors_response = db.table("product_editors").select("user_id").eq("product_id", product_id).execute()
    
    if not editors_response.data:
        return []
    
    # Get user details for each editor
    user_ids = [editor["user_id"] for editor in editors_response.data]
    users_response = db.table("users").select("*").in_("id", user_ids).execute()
    
    return users_response.data or []


# ------------------------------
# Tag helpers
# ------------------------------

def get_product_tag_rows(db, product_ids: list[str]):
    """Fetch product_tags rows for given product IDs"""
    return db.table("product_tags").select("*").in_("product_id", product_ids).execute().data


def get_tags_map(db, tag_ids: list[str]):
    """Fetch tags by IDs and return map id -> name"""
    if not tag_ids:
        return {}
    rows = db.table("tags").select("*").in_("id", tag_ids).execute().data
    return {row["id"]: row["name"] for row in rows}


def get_or_create_tag_ids(db, tag_names: list[str]) -> dict[str, str]:
    """Return map name -> id, creating tags as needed."""
    if not tag_names:
        return {}
    # Existing tags
    existing = db.table("tags").select("*").in_("name", tag_names).execute().data
    by_name = {row["name"]: row["id"] for row in existing}
    # Create missing
    missing = [name for name in tag_names if name not in by_name]
    if missing:
        try:
            created = db.table("tags").insert([{ "name": name } for name in missing]).execute().data
            for row in created:
                by_name[row["name"]] = row["id"]
        except Exception as e:
            # Handle race condition: tags may have been inserted by concurrent request
            # Fetch them again to complete the mapping
            logger = logging.getLogger(__name__)
            logger.warning(f"Tag insert error (likely race condition): {e}, retrying fetch")
            retry = db.table("tags").select("*").in_("name", missing).execute().data
            for row in retry:
                by_name[row["name"]] = row["id"]
    return by_name


def set_product_tags(db, product_id: str, tag_names: list[str]):
    """Delete product's tag relationships and replace with given names (overwrite)."""
    db.table("product_tags").delete().eq("product_id", product_id).execute()
    if not tag_names:
        return
    # Get tag IDs
    name_to_id = get_or_create_tag_ids(db, tag_names)
    # Create relationships
    payload = [{"product_id": product_id, "tag_id": tid} for tid in name_to_id.values()]
    db.table("product_tags").insert(payload).execute()

