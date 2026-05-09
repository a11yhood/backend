"""Image upload and delete endpoints.

Moderator/admin-only image management that converts files to base64 data URLs for
storage in the database as text strings. This avoids the need for a separate
object-storage backend while still supporting rich product images.

Supported formats: image/jpeg, image/png, image/webp
Max size: 5 MB

An optional crop region (x, y, width, height in pixels) may be provided to
trim the image before encoding. If no crop is specified the image is stored as
uploaded (after validating type and size).
"""

import base64
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from services.auth import ensure_moderator_or_admin, get_current_user
from services.database import get_db
from services.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["images"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ImageUploadResponse(BaseModel):
    url: str
    """Base-64 data URL (data:<mime>;base64,...) ready for use in img src or DB storage."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_mime_type(content_type: str | None) -> str:
    """Return the normalised MIME type or raise 415 for unsupported types."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported image type '{mime}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )
    return mime


def _apply_crop(
    image_bytes: bytes,
    mime: str,
    crop_x: int,
    crop_y: int,
    crop_width: int,
    crop_height: int,
) -> bytes:
    """Crop the image to the specified rectangle and return the encoded bytes.

    Args:
        image_bytes: Raw image bytes.
        mime: MIME type of the image (used to pick the save format).
        crop_x: Left edge of the crop region in pixels.
        crop_y: Top edge of the crop region in pixels.
        crop_width: Width of the crop region in pixels (must be > 0).
        crop_height: Height of the crop region in pixels (must be > 0).

    Returns:
        Cropped image bytes re-encoded in the original format.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="Server-side image processing is unavailable (Pillow not installed).",
        ) from exc

    format_map = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }
    pil_format = format_map.get(mime, "PNG")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img_width, img_height = img.size

            # Clamp coordinates to valid image bounds
            x0 = max(0, crop_x)
            y0 = max(0, crop_y)
            x1 = min(img_width, crop_x + crop_width)
            y1 = min(img_height, crop_y + crop_height)

            if x1 <= x0 or y1 <= y0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Crop region is outside the image bounds or has zero area. "
                        f"Image size: {img_width}×{img_height}px; "
                        f"Requested crop: ({crop_x},{crop_y}) {crop_width}×{crop_height}px."
                    ),
                )

            cropped = img.crop((x0, y0, x1, y1))
            buf = io.BytesIO()
            save_kwargs: dict = {}
            if pil_format == "JPEG":
                # Ensure JPEG-compatible mode (no alpha)
                if cropped.mode in ("RGBA", "LA", "P"):
                    cropped = cropped.convert("RGB")
                save_kwargs["quality"] = 90
            cropped.save(buf, format=pil_format, **save_kwargs)
            return buf.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Image crop failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to process image: {exc}") from exc


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=ImageUploadResponse, status_code=200)
@limiter.limit("20/minute")
async def upload_image(
    request: Request,
    file: Annotated[UploadFile, File(description="Image file to upload (JPEG, PNG, or WebP)")],
    crop_x: Annotated[int | None, Form(description="Left edge of crop region in pixels")] = None,
    crop_y: Annotated[int | None, Form(description="Top edge of crop region in pixels")] = None,
    crop_width: Annotated[int | None, Form(description="Width of crop region in pixels")] = None,
    crop_height: Annotated[int | None, Form(description="Height of crop region in pixels")] = None,
    current_user: dict = Depends(get_current_user),
) -> ImageUploadResponse:
    """Upload an image and receive a base-64 data URL.

    **Permissions:** Moderator or Admin only.

    The returned ``url`` value is a ``data:<mime>;base64,...`` string that can
    be stored directly in the database ``image`` column of a product or used as
    an ``<img src>`` attribute.

    **Crop parameters** (all four must be supplied together if any are given):

    | Parameter    | Description |
    |-------------|-------------|
    | ``crop_x``     | Left edge of the desired crop region (pixels from left) |
    | ``crop_y``     | Top edge of the desired crop region (pixels from top) |
    | ``crop_width`` | Width of the crop region in pixels |
    | ``crop_height``| Height of the crop region in pixels |

    **Error codes:**

    | Status | Reason |
    |--------|--------|
    | 400    | Malformed request or crop region invalid |
    | 401    | Not authenticated |
    | 403    | Authenticated but not moderator/admin |
    | 413    | File exceeds 5 MB limit |
    | 415    | Unsupported image type |
    | 429    | Rate limit exceeded (20 uploads/minute) |
    """
    ensure_moderator_or_admin(current_user)

    # Validate MIME type from the declared content type
    mime = _validate_mime_type(file.content_type)

    # Read file bytes
    try:
        image_bytes = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.") from exc

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Enforce size limit (413)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File size {len(image_bytes):,} bytes exceeds the 5 MB limit.",
        )

    # Validate crop parameters — all four must be present if any are given
    crop_params = (crop_x, crop_y, crop_width, crop_height)
    crop_provided = [p is not None for p in crop_params]
    if any(crop_provided) and not all(crop_provided):
        raise HTTPException(
            status_code=400,
            detail=(
                "All four crop parameters (crop_x, crop_y, crop_width, crop_height) "
                "must be supplied together."
            ),
        )

    if all(crop_provided):
        # Validate crop values are positive
        if crop_width <= 0 or crop_height <= 0:  # type: ignore[operator]
            raise HTTPException(
                status_code=400,
                detail="crop_width and crop_height must be greater than zero.",
            )
        image_bytes = _apply_crop(
            image_bytes,
            mime,
            crop_x,  # type: ignore[arg-type]
            crop_y,  # type: ignore[arg-type]
            crop_width,  # type: ignore[arg-type]
            crop_height,  # type: ignore[arg-type]
        )

    # Encode to base64 data URL
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    logger.info(
        "Image uploaded by user %s: mime=%s size=%d bytes (crop=%s)",
        current_user.get("id"),
        mime,
        len(image_bytes),
        all(crop_provided),
    )

    return ImageUploadResponse(url=data_url)


# ---------------------------------------------------------------------------
# Delete endpoints
# ---------------------------------------------------------------------------


@router.delete("/product/{product_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_product_image(
    request: Request,
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> Response:
    """Remove the image from a product (sets ``image_id`` to NULL).

    **Permissions:** Moderator or Admin only.

    **Error codes:**

    | Status | Reason |
    |--------|--------|
    | 401    | Not authenticated |
    | 403    | Authenticated but not moderator/admin |
    | 404    | Product not found |
    | 429    | Rate limit exceeded |
    """
    ensure_moderator_or_admin(current_user)

    existing = db.table("products").select("id").eq("id", product_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Product not found.")

    db.table("products").update({"image_id": None, "image_alt": None}).eq(
        "id", product_id
    ).execute()

    logger.info(
        "Image deleted from product %s by user %s",
        product_id,
        current_user.get("id"),
    )
    return Response(status_code=204)


@router.delete("/blog-post/{post_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_blog_post_image(
    request: Request,
    post_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> Response:
    """Remove the header image from a blog post (sets ``header_image_id`` to NULL).

    **Permissions:** Moderator or Admin only.

    **Error codes:**

    | Status | Reason |
    |--------|--------|
    | 401    | Not authenticated |
    | 403    | Authenticated but not moderator/admin |
    | 404    | Blog post not found |
    | 429    | Rate limit exceeded |
    """
    ensure_moderator_or_admin(current_user)

    existing = db.table("blog_posts").select("id").eq("id", post_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Blog post not found.")

    db.table("blog_posts").update(
        {"header_image_id": None, "header_image_alt": None}
    ).eq("id", post_id).execute()

    logger.info(
        "Image deleted from blog post %s by user %s",
        post_id,
        current_user.get("id"),
    )
    return Response(status_code=204)
