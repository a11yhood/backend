"""Helpers for image URL normalization and image-reference rows.

These helpers keep API compatibility by allowing callers to continue storing and
returning URL strings, while also maintaining normalized references in
`public.images` via image IDs.
"""

import hashlib

_capability_cache: dict[tuple[str, str], bool] = {}


def _classify_source_kind(canonical_url: str) -> str:
    """Classify image source as uploaded vs external based on URL scheme."""
    if canonical_url.lower().startswith("data:"):
        return "uploaded"
    return "external"


def _probe_select(db, table: str, column: str) -> bool:
    """Return True when table+column are available in current DB schema."""
    cache_key = (table, column)
    if cache_key in _capability_cache:
        return _capability_cache[cache_key]

    try:
        db.table(table).select(column).limit(1).execute()
        _capability_cache[cache_key] = True
        return True
    except Exception:
        _capability_cache[cache_key] = False
        return False


def supports_product_image_refs(db) -> bool:
    return _probe_select(db, "images", "id") and _probe_select(db, "products", "image_id")


def supports_blog_image_refs(db) -> bool:
    return _probe_select(db, "images", "id") and _probe_select(db, "blog_posts", "header_image_id")


def _split_data_url(src: str) -> tuple[str | None, str] | None:
    """Return (mime_type, base64_payload) for a data URL, or None."""
    if not src.lower().startswith("data:"):
        return None
    if "," not in src:
        return None

    metadata, payload = src.split(",", 1)
    payload = payload.strip()
    if not payload:
        return None

    mime_type: str | None = None
    if ";" in metadata:
        mime_type = metadata.split(";", 1)[0].split(":", 1)[-1].strip() or None
    else:
        mime_type = metadata.split(":", 1)[-1].strip() or None

    return mime_type, payload


def _canonical_key_for_value(src: str) -> str:
    """Build deterministic compact dedupe key for an image source value."""
    data_parts = _split_data_url(src)
    if data_parts is not None:
        _, payload = data_parts
        digest = hashlib.md5(payload.encode("ascii", errors="ignore")).hexdigest()
        return f"uploaded:{digest}"

    digest = hashlib.md5(src.encode("utf-8")).hexdigest()
    return f"external:{digest}"


def get_or_create_image_id(db, canonical_url: str | None, created_by: str | None = None) -> str | None:
    """Return image ID for a canonical URL, creating a row if missing.

    This function does not download/copy external images. For external URLs,
    it stores the URL as a reference only.
    """
    if not canonical_url:
        return None

    src = str(canonical_url).strip()
    if not src:
        return None

    has_canonical_key = _probe_select(db, "images", "canonical_key")

    if has_canonical_key:
        canonical_key = _canonical_key_for_value(src)
        existing = db.table("images").select("id").eq("canonical_key", canonical_key).limit(1).execute()
        if existing.data:
            return existing.data[0].get("id")

        payload = {
            "canonical_key": canonical_key,
            "source_kind": _classify_source_kind(src),
        }
        data_parts = _split_data_url(src)
        if data_parts is not None:
            mime_type, image_payload = data_parts
            payload["canonical_url"] = None
            payload["image_data_base64"] = image_payload
            if mime_type:
                payload["mime_type"] = mime_type
        else:
            payload["canonical_url"] = src
            payload["image_data_base64"] = None

        if created_by:
            payload["created_by"] = created_by

        inserted = db.table("images").insert(payload).execute()
        if inserted.data:
            return inserted.data[0].get("id")

        fallback = db.table("images").select("id").eq("canonical_key", canonical_key).limit(1).execute()
        if fallback.data:
            return fallback.data[0].get("id")

        return None

    existing = db.table("images").select("id").eq("canonical_url", src).limit(1).execute()
    if existing.data:
        return existing.data[0].get("id")

    payload = {
        "canonical_url": src,
        "source_kind": _classify_source_kind(src),
    }
    if created_by:
        payload["created_by"] = created_by

    inserted = db.table("images").insert(payload).execute()
    if inserted.data:
        return inserted.data[0].get("id")

    # Fallback in case of races where another request inserted the same URL.
    fallback = db.table("images").select("id").eq("canonical_url", src).limit(1).execute()
    if fallback.data:
        return fallback.data[0].get("id")

    return None
