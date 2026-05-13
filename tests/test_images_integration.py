"""Integration tests for image upload/delete endpoints and image references."""

import base64
import io
import struct
import uuid
import zlib

import pytest

pytestmark = pytest.mark.integration

def _make_png_bytes(width: int = 1, height: int = 1) -> bytes:
    """Return a minimal valid PNG file of the given dimensions."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        chunk = struct.pack(">I", len(data)) + tag + data
        return chunk + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
    )

    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00" + b"\xFF\x00\x00" * width

    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


_PNG_1PX = _make_png_bytes(1, 1)


def test_image_upload_admin_success(client, test_admin, auth_headers):
    response = client.post(
        "/api/images/upload",
        headers=auth_headers(test_admin),
        files={"file": ("tiny.png", io.BytesIO(_PNG_1PX), "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["image_id"]

    image_response = client.get(f"/api/images/{payload['image_id']}")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/png")
    assert image_response.content == _PNG_1PX


def test_image_upload_regular_user_forbidden(client, test_user, auth_headers):
    response = client.post(
        "/api/images/upload",
        headers=auth_headers(test_user),
        files={"file": ("tiny.png", io.BytesIO(_PNG_1PX), "image/png")},
    )

    assert response.status_code == 403


def test_delete_product_image_clears_image_fields(client, clean_database, test_user, test_admin, auth_headers):
    source_url = f"https://github.com/a11yhood/image-test-{uuid.uuid4()}"
    product_response = client.post(
        "/api/products",
        headers=auth_headers(test_user),
        json={
            "name": "Image Delete Integration Product",
            "description": "integration test product",
            "source_url": source_url,
            "type": "Software",
            "image": {
                "url": "https://example.com/product-image.png",
                "alt": "product alt",
            },
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]
    assert product_response.json()["image_alt"] == "product alt"

    before = clean_database.table("products").select("image_id").eq("id", product_id).execute()
    assert before.data
    assert before.data[0]["image_id"] is not None

    delete_response = client.delete(
        f"/api/images/product/{product_id}",
        headers=auth_headers(test_admin),
    )
    assert delete_response.status_code == 204

    after = clean_database.table("products").select("image_id").eq("id", product_id).execute()
    assert after.data
    # Only the FK is cleared; the shared image row remains intact.
    assert after.data[0]["image_id"] is None


def test_product_response_includes_image_identifiers(client, test_user, auth_headers):
    source_url = f"https://github.com/a11yhood/image-id-test-{uuid.uuid4()}"
    create_response = client.post(
        "/api/products",
        headers=auth_headers(test_user),
        json={
            "name": "Image Identifier Product",
            "description": "integration test product",
            "source_url": source_url,
            "type": "Software",
            "image": {
                "url": "https://example.com/product-image-id.png",
                "alt": "image id alt",
            },
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["image_id"] is not None
    assert "image" not in created
    assert "image_url" not in created

    get_response = client.get(f"/api/products/{created['id']}")
    assert get_response.status_code == 200
    loaded = get_response.json()
    assert loaded["image_id"] == created["image_id"]
    assert "image" not in loaded
    assert "image_url" not in loaded


def test_get_image_by_id_serves_uploaded_image_bytes(client, test_user, auth_headers):
    source_url = f"https://github.com/a11yhood/image-by-id-uploaded-{uuid.uuid4()}"
    data_url = f"data:image/png;base64,{base64.b64encode(_PNG_1PX).decode('ascii')}"
    create_response = client.post(
        "/api/products",
        headers=auth_headers(test_user),
        json={
            "name": "Image by ID Uploaded",
            "description": "integration test product",
            "source_url": source_url,
            "type": "Software",
            "image": {"url": data_url},
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()

    image_response = client.get(f"/api/images/{created['image_id']}")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/png")
    assert image_response.content == _PNG_1PX


def test_get_image_by_id_redirects_external_image(client, test_user, auth_headers):
    source_url = f"https://github.com/a11yhood/image-by-id-external-{uuid.uuid4()}"
    external_image_url = "https://example.com/external-image.png"
    create_response = client.post(
        "/api/products",
        headers=auth_headers(test_user),
        json={
            "name": "Image by ID External",
            "description": "integration test product",
            "source_url": source_url,
            "type": "Software",
            "image": {"url": external_image_url},
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()

    image_response = client.get(f"/api/images/{created['image_id']}", follow_redirects=False)
    assert image_response.status_code == 307
    assert image_response.headers.get("location") == external_image_url


def test_delete_blog_post_image_clears_image_fields(client, clean_database, test_admin, auth_headers):
    slug = f"image-delete-blog-{uuid.uuid4()}"
    create_response = client.post(
        "/api/blog-posts",
        headers=auth_headers(test_admin),
        json={
            "title": "Image Delete Integration Blog",
            "slug": slug,
            "content": "blog content",
            "author_id": test_admin["id"],
            "author_name": test_admin["display_name"],
            "published": False,
            "header_image": "https://example.com/blog-image.png",
            "header_image_alt": "blog alt",
        },
    )
    assert create_response.status_code == 201
    post_id = create_response.json()["id"]
    assert create_response.json()["header_image_alt"] == "blog alt"

    before = (
        clean_database.table("blog_posts")
        .select("header_image_id")
        .eq("id", post_id)
        .execute()
    )
    assert before.data
    assert before.data[0]["header_image_id"] is not None

    delete_response = client.delete(
        f"/api/images/blog-post/{post_id}",
        headers=auth_headers(test_admin),
    )
    assert delete_response.status_code == 204

    after = (
        clean_database.table("blog_posts")
        .select("header_image_id")
        .eq("id", post_id)
        .execute()
    )
    assert after.data
    # Only the FK is cleared; the shared image row remains intact.
    assert after.data[0]["header_image_id"] is None
