from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from models.product_queries import ProductQueryDefinition


def normalize_query_list(values: Iterable[str] | str | None) -> list[str]:
    """Flatten query params supporting comma-separated and repeated values."""
    normalized: list[str] = []
    if values is None:
        return normalized
    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = values
    for value in raw_values:
        if value is None:
            continue
        if not isinstance(value, str):
            value = str(value)
        for part in value.split(","):
            item = part.strip()
            if item:
                normalized.append(item)
    return normalized


def canonicalize_sources(db, values: list[str]) -> list[str]:
    """Map incoming source filter values to canonical names from supported_sources."""
    if not values or db is None:
        return values

    rows = db.table("supported_sources").select("name").execute()
    name_map = {
        str(row.get("name")).strip().lower(): str(row.get("name")).strip()
        for row in (rows.data or [])
        if row.get("name")
    }
    return [name_map.get(value.strip().lower(), value) for value in values]


def get_product_ids_for_tags(db, tag_names: list[str], mode: str = "or") -> set[str]:
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
            product_id = row.get("product_id")
            tag_id = row.get("tag_id")
            if product_id and tag_id:
                product_tag_map.setdefault(product_id, set()).add(tag_id)
        return {product_id for product_id, tag_ids_for_product in product_tag_map.items() if required.issubset(tag_ids_for_product)}

    return {row["product_id"] for row in pt_rows.data if row.get("product_id")}


def prepare_product_filters(
    db,
    current_user: dict | None,
    query_definition: ProductQueryDefinition,
    *,
    allow_aliases: bool = True,
) -> dict[str, Any]:
    updated_since = query_definition.updated_since
    if query_definition.max_age is not None:
        updated_since = (datetime.now(UTC) - timedelta(days=query_definition.max_age)).isoformat()

    tag_mode = (query_definition.tags_mode or "or").lower()
    if tag_mode not in {"or", "and"}:
        raise HTTPException(status_code=400, detail="tags_mode must be 'or' or 'and'")

    if allow_aliases:
        source_values = set(normalize_query_list(query_definition.source) + normalize_query_list(query_definition.sources))
        type_values = set(normalize_query_list(query_definition.type) + normalize_query_list(query_definition.types))
    else:
        if normalize_query_list(query_definition.sources):
            raise HTTPException(
                status_code=400,
                detail="Use repeated 'source' parameters; 'sources' is not supported",
            )
        if normalize_query_list(query_definition.types):
            raise HTTPException(
                status_code=400,
                detail="Use repeated 'type' parameters; 'types' is not supported",
            )
        source_values = set(normalize_query_list(query_definition.source))
        type_values = set(normalize_query_list(query_definition.type))

    source_values = set(canonicalize_sources(db, list(source_values)))
    tag_values = normalize_query_list(query_definition.tags)

    if query_definition.include_banned:
        if not current_user or current_user.get("role") not in {"admin", "moderator"}:
            raise HTTPException(
                status_code=403, detail="Moderator or admin role required to view banned products"
            )

    return {
        "source_values": source_values,
        "type_values": type_values,
        "tag_values": tag_values,
        "tag_mode": tag_mode,
        "min_rating": query_definition.min_rating,
        "updated_since": updated_since,
        "search": query_definition.search,
        "created_by": query_definition.created_by,
        "editor_id": query_definition.editor_id,
        "include_banned": query_definition.include_banned,
    }


def apply_product_filters(query, db, filters: dict[str, Any], *, tag_lookup=get_product_ids_for_tags):
    source_values = filters.get("source_values", set())
    type_values = filters.get("type_values", set())
    tag_values = filters.get("tag_values", [])

    if source_values:
        query = query.in_("source", list(source_values))

    if type_values:
        query = query.in_("type", list(type_values))

    if tag_values:
        product_ids_with_tags = tag_lookup(db, tag_values, filters.get("tag_mode", "or"))
        if not product_ids_with_tags:
            return None
        query = query.in_("id", list(product_ids_with_tags))

    if filters.get("search"):
        query = query.ilike("name", f"%{filters['search']}%")

    if filters.get("created_by"):
        query = query.eq("created_by", filters["created_by"])

    if filters.get("editor_id"):
        editor_rows = (
            db.table("product_editors").select("product_id").eq("user_id", filters["editor_id"]).execute()
        )
        editor_product_ids = [
            row["product_id"] for row in (editor_rows.data or []) if row.get("product_id")
        ]
        if not editor_product_ids:
            return None
        query = query.in_("id", editor_product_ids)

    if not filters.get("include_banned", False):
        query = query.eq("banned", False)

    if filters.get("updated_since") is not None:
        query = query.gte("source_last_updated", filters["updated_since"])

    if filters.get("min_rating") is not None:
        query = query.gte("computed_rating", filters["min_rating"])

    return query


def fetch_filtered_product_ids(
    db,
    filters: dict[str, Any],
    *,
    sort_field: str = "created_at",
    sort_desc: bool = True,
    apply_filters=apply_product_filters,
) -> list[str]:
    query = apply_filters(db.table("products").select("id"), db, filters)
    if query is None:
        return []

    query = query.order(sort_field, desc=sort_desc)

    if getattr(db, "backend", None) != "supabase":
        response = query.execute()
        return [row["id"] for row in (response.data or []) if row.get("id")]

    product_ids: list[str] = []
    page_size = 500
    offset = 0
    while True:
        response = query.range(offset, offset + page_size - 1).execute()
        rows = response.data or []
        if not rows:
            break
        product_ids.extend([row["id"] for row in rows if row.get("id")])
        if len(rows) < page_size:
            break
        offset += page_size
    return product_ids


def without_min_rating(filters: dict[str, Any]) -> dict[str, Any]:
    base_filters = dict(filters)
    base_filters["min_rating"] = None
    return base_filters