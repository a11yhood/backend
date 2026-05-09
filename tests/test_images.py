"""Unit tests for the image upload and delete endpoints.

These tests override the ``get_current_user`` and ``get_db`` FastAPI dependencies
directly so that no real database calls or Supabase credentials are needed.
"""

import base64
import io
from unittest.mock import MagicMock

import pytest

from main import app
from services.auth import get_current_user
from services.database import get_db

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Tiny synthetic images for testing
# ---------------------------------------------------------------------------

# Minimal 1×1 pixel JPEG (in bytes)
_JPEG_1PX = bytes(
    [
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xFF, 0xD9,
    ]
)


def _make_png_bytes(width: int = 2, height: int = 2) -> bytes:
    """Return a minimal valid PNG file of the given dimensions."""
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
    )
    # Raw image data: one filter byte per row + RGB pixels
    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00" + b"\xFF\x00\x00" * width  # red pixels
    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# A small valid PNG (2×2 pixels)
_PNG_2PX = _make_png_bytes(2, 2)

# A larger PNG (10×10 pixels) for crop tests
_PNG_10PX = _make_png_bytes(10, 10)

# A fake "large" file just over the 5MB limit
_OVER_LIMIT_BYTES = b"X" * (5 * 1024 * 1024 + 1)


# ---------------------------------------------------------------------------
# Auth-mocking fixtures
# ---------------------------------------------------------------------------

_MODERATOR_USER = {"id": "mod-id", "role": "moderator", "username": "mod_user"}
_ADMIN_USER = {"id": "admin-id", "role": "admin", "username": "admin_user"}
_REGULAR_USER = {"id": "user-id", "role": "user", "username": "reg_user"}


@pytest.fixture
def upload_client(unit_client):
    """unit_client with get_current_user overridden to a moderator."""
    app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
    yield unit_client
    # Restore – unit_client's own teardown will call app.dependency_overrides.clear(),
    # but we reset the specific override here so other tests aren't affected.
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def admin_upload_client(unit_client):
    """unit_client with get_current_user overridden to an admin."""
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    yield unit_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def user_upload_client(unit_client):
    """unit_client with get_current_user overridden to a regular (non-mod) user."""
    app.dependency_overrides[get_current_user] = lambda: _REGULAR_USER
    yield unit_client
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Authentication / authorisation
# ---------------------------------------------------------------------------


def test_upload_requires_authentication(unit_client):
    """Unauthenticated request must return 401."""
    resp = unit_client.post(
        "/api/images/upload",
        files={"file": ("test.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 401


def test_regular_user_gets_403(user_upload_client):
    """Regular user (not moderator/admin) must receive 403."""
    resp = user_upload_client.post(
        "/api/images/upload",
        files={"file": ("test.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


def test_moderator_can_upload(upload_client):
    """Moderator should be able to upload successfully."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("test.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert data["url"].startswith("data:image/png;base64,")


def test_admin_can_upload(admin_upload_client):
    """Admin should be able to upload successfully."""
    resp = admin_upload_client.post(
        "/api/images/upload",
        files={"file": ("test.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# MIME type validation
# ---------------------------------------------------------------------------


def test_jpeg_accepted(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("photo.jpg", io.BytesIO(_JPEG_1PX), "image/jpeg")},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("data:image/jpeg;base64,")


def test_png_accepted(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("data:image/png;base64,")


def test_gif_rejected_with_415(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("anim.gif", io.BytesIO(b"GIF89a"), "image/gif")},
    )
    assert resp.status_code == 415
    body = resp.json()
    assert "detail" in body


def test_pdf_rejected_with_415(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-"), "application/pdf")},
    )
    assert resp.status_code == 415


def test_octet_stream_rejected_with_415(upload_client):
    """application/octet-stream (unknown content type) should be rejected with 415."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img", io.BytesIO(_PNG_2PX), "application/octet-stream")},
    )
    assert resp.status_code == 415


# ---------------------------------------------------------------------------
# File size validation
# ---------------------------------------------------------------------------


def test_file_over_5mb_rejected_with_413(upload_client):
    """Files exceeding 5MB must be rejected with 413."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("big.png", io.BytesIO(_OVER_LIMIT_BYTES), "image/png")},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert "detail" in body


def test_empty_file_rejected_with_400(upload_client):
    """An empty file body must be rejected with 400."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Data-URL encoding
# ---------------------------------------------------------------------------


def test_response_url_is_valid_base64(upload_client):
    """Returned data URL must decode to the original file bytes."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 200
    data_url = resp.json()["url"]
    # Strip "data:image/png;base64," prefix
    _, b64_part = data_url.split(",", 1)
    decoded = base64.b64decode(b64_part)
    assert decoded == _PNG_2PX


# ---------------------------------------------------------------------------
# Crop parameters
# ---------------------------------------------------------------------------


def test_valid_crop_applied(upload_client):
    """Providing all four crop params should succeed and return a data URL."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("big.png", io.BytesIO(_PNG_10PX), "image/png")},
        data={"crop_x": "0", "crop_y": "0", "crop_width": "5", "crop_height": "5"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("data:image/png;base64,")


def test_partial_crop_params_rejected(upload_client):
    """Providing only some crop parameters must return 400."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_10PX), "image/png")},
        data={"crop_x": "0", "crop_y": "0"},  # missing crop_width and crop_height
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body


def test_zero_crop_dimension_rejected(upload_client):
    """A crop region with zero width or height must return 400."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_10PX), "image/png")},
        data={"crop_x": "0", "crop_y": "0", "crop_width": "0", "crop_height": "5"},
    )
    assert resp.status_code == 400


def test_out_of_bounds_crop_rejected(upload_client):
    """A crop region that falls entirely outside the image must return 400."""
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_10PX), "image/png")},
        data={
            "crop_x": "100",
            "crop_y": "100",
            "crop_width": "50",
            "crop_height": "50",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Error body structure — must always contain a 'detail' field with a message
# ---------------------------------------------------------------------------


def test_403_has_detail_field(user_upload_client):
    """403 error responses must include a 'detail' key with a human-readable message."""
    resp = user_upload_client.post(
        "/api/images/upload",
        files={"file": ("img.png", io.BytesIO(_PNG_2PX), "image/png")},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)
    assert len(body["detail"]) > 0


def test_415_has_detail_field(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("img.bmp", io.BytesIO(b"BM"), "image/bmp")},
    )
    assert resp.status_code == 415
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


def test_413_has_detail_field(upload_client):
    resp = upload_client.post(
        "/api/images/upload",
        files={"file": ("big.png", io.BytesIO(_OVER_LIMIT_BYTES), "image/png")},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


# ---------------------------------------------------------------------------
# Helper-function unit tests (no HTTP, no fixtures)
# ---------------------------------------------------------------------------


class TestValidateMimeType:
    def test_accepts_jpeg(self):
        from routers.images import _validate_mime_type

        assert _validate_mime_type("image/jpeg") == "image/jpeg"

    def test_accepts_png(self):
        from routers.images import _validate_mime_type

        assert _validate_mime_type("image/png") == "image/png"

    def test_accepts_webp(self):
        from routers.images import _validate_mime_type

        assert _validate_mime_type("image/webp") == "image/webp"

    def test_rejects_gif(self):
        from fastapi import HTTPException

        from routers.images import _validate_mime_type

        with pytest.raises(HTTPException) as exc_info:
            _validate_mime_type("image/gif")
        assert exc_info.value.status_code == 415

    def test_strips_charset_suffix(self):
        from routers.images import _validate_mime_type

        assert _validate_mime_type("image/png; charset=utf-8") == "image/png"

    def test_rejects_empty_string(self):
        from fastapi import HTTPException

        from routers.images import _validate_mime_type

        with pytest.raises(HTTPException) as exc_info:
            _validate_mime_type("")
        assert exc_info.value.status_code == 415

    def test_rejects_none(self):
        from fastapi import HTTPException

        from routers.images import _validate_mime_type

        with pytest.raises(HTTPException) as exc_info:
            _validate_mime_type(None)
        assert exc_info.value.status_code == 415


class TestApplyCrop:
    def test_basic_crop_returns_bytes(self):
        from routers.images import _apply_crop

        result = _apply_crop(_PNG_10PX, "image/png", 0, 0, 5, 5)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_out_of_bounds_raises_400(self):
        from fastapi import HTTPException

        from routers.images import _apply_crop

        with pytest.raises(HTTPException) as exc_info:
            _apply_crop(_PNG_10PX, "image/png", 200, 200, 50, 50)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Delete endpoint helpers
# ---------------------------------------------------------------------------


def _make_db_mock(*, found: bool = True) -> MagicMock:
    """Return a mock DB client that simulates a found or missing row."""
    db = MagicMock()
    select_result = MagicMock()
    select_result.data = [{"id": "some-id"}] if found else []
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value
    ) = select_result
    return db


# ---------------------------------------------------------------------------
# DELETE /api/images/product/{product_id}
# ---------------------------------------------------------------------------


class TestDeleteProductImage:
    def _client(self, unit_client, user: dict, found: bool = True):
        db_mock = _make_db_mock(found=found)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db_mock
        yield unit_client, db_mock
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_moderator_can_delete_product_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/product/prod-123")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 204

    def test_admin_can_delete_product_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/product/prod-456")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 204

    def test_regular_user_cannot_delete_product_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _REGULAR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/product/prod-123")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 403

    def test_unauthenticated_delete_product_image_returns_401(self, unit_client):
        resp = unit_client.delete("/api/images/product/prod-123")
        assert resp.status_code == 401

    def test_missing_product_returns_404(self, unit_client):
        db_mock = _make_db_mock(found=False)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/product/nonexistent")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_delete_calls_update_with_null_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            unit_client.delete("/api/images/product/prod-123")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        # Verify the update was called with NULL image_id
        db_mock.table.assert_any_call("products")
        update_call = db_mock.table.return_value.update
        update_call.assert_called_with({"image_id": None})


# ---------------------------------------------------------------------------
# DELETE /api/images/blog-post/{post_id}
# ---------------------------------------------------------------------------


class TestDeleteBlogPostImage:
    def test_moderator_can_delete_blog_post_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/blog-post/post-abc")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 204

    def test_admin_can_delete_blog_post_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/blog-post/post-abc")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 204

    def test_regular_user_cannot_delete_blog_post_image(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _REGULAR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/blog-post/post-abc")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 403

    def test_unauthenticated_delete_blog_post_image_returns_401(self, unit_client):
        resp = unit_client.delete("/api/images/blog-post/post-abc")
        assert resp.status_code == 401

    def test_missing_blog_post_returns_404(self, unit_client):
        db_mock = _make_db_mock(found=False)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            resp = unit_client.delete("/api/images/blog-post/nonexistent")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_delete_calls_update_with_null_image_fields(self, unit_client):
        db_mock = _make_db_mock(found=True)
        app.dependency_overrides[get_current_user] = lambda: _MODERATOR_USER
        app.dependency_overrides[get_db] = lambda: db_mock
        try:
            unit_client.delete("/api/images/blog-post/post-abc")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
        db_mock.table.assert_any_call("blog_posts")
        update_call = db_mock.table.return_value.update
        update_call.assert_called_with({"header_image_id": None})
