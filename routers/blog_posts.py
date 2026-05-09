"""Blog post management endpoints.

Admin-only blog posts with markdown content, header images, and multi-author support.
Security: All mutations require admin role; image uploads size-limited to ~5MB.
Markdown content should be sanitized before rendering to prevent XSS.
"""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from models.blog_posts import BlogPostCreate, BlogPostResponse, BlogPostUpdate
from services.auth import ensure_admin, get_current_user, get_current_user_optional
from services.database import get_db
from services.image_references import get_or_create_image_id, resolve_image_value
from services.sanitizer import sanitize_html
from services.timestamps import normalize_timestamp_value

router = APIRouter(prefix="/api/blog-posts", tags=["blog"])


def _to_iso_utc(value: object | None) -> str | None:
    """Normalize any datetime value to a canonical ISO 8601 UTC string."""
    normalized = normalize_timestamp_value(value)
    return normalized if isinstance(normalized, str) else None


def _slugify(text: str) -> str:
    """Generate URL-friendly slug from blog post title.

    Normalizes title to lowercase, removes special chars, and replaces spaces with hyphens.
    Example: "Hello World & Friends" -> "hello-world-and-friends"
    Used for clean URLs: /blog/hello-world-and-friends
    """
    return (
        (
            text.lower()
            .strip()
            .replace("'", "")
            .replace('"', "")
            .replace("&", " and ")
            .replace("/", "-")
            .replace("\\", "-")
        )
        .replace(" ", "-")
        .replace("--", "-")
    )


def _normalize_image_string(value: str | None) -> str | None:
    """Normalize header image values to a consistent, browser-friendly format.

    Handles multiple input formats:
    - HTTP(S) URLs: passed through unchanged
    - Data URLs: passed through unchanged
    - Raw base64: auto-detects mime type from magic bytes and adds data URL prefix

    MIME detection examines base64 prefix:
    - /9j/ -> JPEG, iVBOR -> PNG, R0lGOD -> GIF, Qk -> BMP
    - Default: PNG if unrecognized
    """
    if not value:
        return None
    src = value.strip()
    if not src:
        return None
    if src.lower().startswith("http://") or src.lower().startswith("https://"):
        return src
    if src.lower().startswith("data:"):
        return src
    head = src[:10]
    mime = "image/png"
    if head.startswith("/9j/"):
        mime = "image/jpeg"
    elif head.startswith("iVBOR"):
        mime = "image/png"
    elif head.startswith("R0lGOD"):
        mime = "image/gif"
    elif head.startswith("Qk"):
        mime = "image/bmp"
    return f"data:{mime};base64,{src}"


def _validate_image_size(data_url: str | None, field_name: str = "header_image"):
    """Enforce a ~5MB maximum payload for images.

    We estimate byte size from the base64 payload length: bytes ~= len * 3 / 4.
    """
    if not data_url or not data_url.startswith("data:"):
        return
    try:
        comma = data_url.find(",")
        if comma == -1:
            return
        b64 = data_url[comma + 1 :]
        approx_bytes = int(len(b64) * 3 / 4)
        if approx_bytes > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{field_name} exceeds 5MB limit")
    except Exception:
        # On parsing errors, do not block; validation is best-effort
        return


_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HTML_IMG_RE = re.compile(r"<img[^>]+src=[\"\']([^\"\']+)[\"\'][^>]*>", re.IGNORECASE)


def _normalize_content_images(content: str | None) -> str | None:
    """Normalize and validate inline images embedded in markdown/HTML content.

    - Converts raw base64 URLs to data URLs with a mime prefix
    - Validates each data URL is <= 5MB
    - Leaves http(s) and already-normalized data URLs untouched
    """
    if not content:
        return content

    def _md_replacer(match: re.Match) -> str:
        url = match.group(1)
        norm = _normalize_image_string(url)
        if norm and norm.startswith("data:"):
            _validate_image_size(norm, field_name="content image")
        # Rebuild the original "![alt](...)" with normalized URL
        start, end = match.span(1)
        return content[match.start() : start] + (norm or url) + content[end : match.end()]

    # We'll replace by building progressively to avoid nested span confusion.
    # First handle markdown images.
    parts = []
    last = 0
    for m in _MD_IMAGE_RE.finditer(content):
        url = m.group(1)
        norm = _normalize_image_string(url)
        if norm and norm.startswith("data:"):
            _validate_image_size(norm, field_name="content image")
        # Replace only the URL portion
        start_url, end_url = m.span(1)
        parts.append(content[last:start_url])
        parts.append(norm or url)
        last = end_url
    md_normalized = "".join(parts) + content[last:]

    # Now handle <img src="..."> inside the markdown content
    parts = []
    last = 0
    for m in _HTML_IMG_RE.finditer(md_normalized):
        url = m.group(1)
        norm = _normalize_image_string(url)
        if norm and norm.startswith("data:"):
            _validate_image_size(norm, field_name="content image")
        start_url, end_url = m.span(1)
        parts.append(md_normalized[last:start_url])
        parts.append(norm or url)
        last = end_url
    html_normalized = "".join(parts) + md_normalized[last:]

    return html_normalized


def _normalize_post(record: dict, db=None) -> dict:
    if not record:
        return record

    post = dict(record)
    post["tags"] = post.get("tags") or []
    post["author_ids"] = post.get("author_ids") or (
        [post["author_id"]] if post.get("author_id") else []
    )
    post["author_names"] = post.get("author_names") or (
        [post["author_name"]] if post.get("author_name") else []
    )

    for field in ["created_at", "updated_at", "published_at", "publish_date"]:
        post[field] = _to_iso_utc(post.get(field))

    # Ensure header_image is always a valid src for clients.
    if db is not None:
        resolved_header = resolve_image_value(db, post.get("header_image_id"))
    else:
        resolved_header = post.get("header_image")
    post["header_image"] = _normalize_image_string(resolved_header)

    return post


def _ensure_slug_unique(db, slug: str, exclude_id: str | None = None):
    query = db.table("blog_posts").select("id").eq("slug", slug)
    if exclude_id:
        query = query.neq("id", exclude_id)
    existing = query.execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Slug already exists")


@router.get("", response_model=list[BlogPostResponse])
async def list_blog_posts(
    include_unpublished: bool = Query(False, alias="includeUnpublished"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    response: Response = None,
    current_user: dict | None = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    if include_unpublished:
        ensure_admin(current_user)

    query = db.table("blog_posts").select("*")
    if not include_unpublished:
        query = query.eq("published", True)

    # Push ordering to SQL: primary publish_date desc NULLS LAST, then published_at desc, then created_at desc
    # Supabase/PostgREST supports multiple order clauses by repeating `order`.
    query = (
        query.order("publish_date", desc=True, nullsfirst=False)
        .order("published_at", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
    )
    query = query.range(offset, offset + limit - 1)

    db_resp = query.execute()
    posts = [_normalize_post(p, db) for p in (db_resp.data or [])]
    # Cache for 5 minutes for public listing
    if response is not None and not include_unpublished:
        response.headers["Cache-Control"] = "public, max-age=300"
    return posts


@router.get("/{post_id}", response_model=BlogPostResponse)
async def get_blog_post(
    post_id: str,
    current_user: dict | None = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    response = db.table("blog_posts").select("*").eq("id", post_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Blog post not found")

    post = _normalize_post(response.data[0], db)
    if not post.get("published") and not (current_user and current_user.get("role") == "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return post


@router.get("/slug/{slug}", response_model=BlogPostResponse)
async def get_blog_post_by_slug(
    slug: str,
    current_user: dict | None = Depends(get_current_user_optional),
    db=Depends(get_db),
):
    response = db.table("blog_posts").select("*").eq("slug", slug).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Blog post not found")

    post = _normalize_post(response.data[0], db)
    if not post.get("published") and not (current_user and current_user.get("role") == "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return post


@router.post("", response_model=BlogPostResponse, status_code=201)
async def create_blog_post(
    payload: BlogPostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    ensure_admin(current_user)

    slug = (payload.slug or _slugify(payload.title)).strip()
    if not slug:
        raise HTTPException(status_code=400, detail="Slug is required")
    _ensure_slug_unique(db, slug)

    now = datetime.now(UTC)
    published_at_iso = _to_iso_utc(payload.published_at) or (_to_iso_utc(now) if payload.published else None)

    author_ids = payload.author_ids or [payload.author_id]
    author_names = payload.author_names or [payload.author_name]

    normalized_image = _normalize_image_string(payload.header_image)
    _validate_image_size(normalized_image)
    header_image_id = get_or_create_image_id(
        db, normalized_image, created_by=current_user.get("id"), alt_text=payload.header_image_alt
    )

    normalized_content = _normalize_content_images(payload.content)

    # Sanitize markdown content to prevent XSS
    sanitized_content = sanitize_html(normalized_content or payload.content)

    record = {
        "title": payload.title,
        "slug": slug,
        "content": sanitized_content,
        "excerpt": payload.excerpt,
        "header_image": normalized_image,
        "header_image_id": header_image_id,
        "header_image_alt": payload.header_image_alt,
        "author_id": payload.author_id,
        "author_name": payload.author_name,
        "author_ids": author_ids,
        "author_names": author_names,
        "tags": payload.tags or [],
        "published": payload.published,
        "published_at": published_at_iso,
        "publish_date": _to_iso_utc(payload.publish_date),
        "featured": payload.featured,
        "created_at": _to_iso_utc(now),
        "updated_at": _to_iso_utc(now),
    }

    response = db.table("blog_posts").insert(record).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create blog post")

    return _normalize_post(response.data[0], db)


@router.patch("/{post_id}", response_model=BlogPostResponse)
async def update_blog_post(
    post_id: str,
    updates: BlogPostUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    ensure_admin(current_user)

    existing = db.table("blog_posts").select("*").eq("id", post_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Blog post not found")

    update_data = {}

    if updates.title is not None:
        update_data["title"] = updates.title
    if updates.slug is not None:
        new_slug = updates.slug.strip()
        if not new_slug:
            raise HTTPException(status_code=400, detail="Slug cannot be empty")
        _ensure_slug_unique(db, new_slug, exclude_id=post_id)
        update_data["slug"] = new_slug
    if updates.content is not None:
        normalized = _normalize_content_images(updates.content) or updates.content
        update_data["content"] = sanitize_html(normalized)
    if updates.excerpt is not None:
        update_data["excerpt"] = updates.excerpt
    if updates.header_image is not None:
        normalized_image = _normalize_image_string(updates.header_image)
        _validate_image_size(normalized_image)
        update_data["header_image_id"] = get_or_create_image_id(
            db, normalized_image, created_by=current_user.get("id"), alt_text=updates.header_image_alt
        )
    if updates.header_image_alt is not None:
        update_data["header_image_alt"] = updates.header_image_alt
    if updates.tags is not None:
        update_data["tags"] = updates.tags
    if updates.featured is not None:
        update_data["featured"] = updates.featured
    if updates.author_id is not None:
        update_data["author_id"] = updates.author_id
    if updates.author_name is not None:
        update_data["author_name"] = updates.author_name
    if updates.author_ids is not None:
        update_data["author_ids"] = updates.author_ids
    if updates.author_names is not None:
        update_data["author_names"] = updates.author_names
    if updates.publish_date is not None:
        update_data["publish_date"] = _to_iso_utc(updates.publish_date)
    if updates.published_at is not None:
        update_data["published_at"] = _to_iso_utc(updates.published_at)
    if updates.published is not None:
        update_data["published"] = updates.published
        if updates.published:
            if "published_at" not in update_data or update_data["published_at"] is None:
                update_data["published_at"] = _to_iso_utc(datetime.now(UTC))
        else:
            update_data["published_at"] = None

    update_data["updated_at"] = _to_iso_utc(datetime.now(UTC))

    updated = db.table("blog_posts").update(update_data).eq("id", post_id).execute()
    if not updated.data:
        raise HTTPException(status_code=400, detail="Failed to update blog post")

    return _normalize_post(updated.data[0], db)


@router.delete("/{post_id}")
async def delete_blog_post(
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    ensure_admin(current_user)

    existing = db.table("blog_posts").select("id").eq("id", post_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Blog post not found")

    db.table("blog_posts").delete().eq("id", post_id).execute()
    return {"success": True}
