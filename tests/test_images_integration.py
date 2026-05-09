"""Integration tests for image upload/delete endpoints and image references."""

import io
import uuid

import pytest

pytestmark = pytest.mark.integration

# Minimal valid 1x1 PNG bytes
_PNG_1PX = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\x1dc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_image_upload_admin_success(client, test_admin, auth_headers):
    response = client.post(
        "/api/images/upload",
        headers=auth_headers(test_admin),
        files={"file": ("tiny.png", io.BytesIO(_PNG_1PX), "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"].startswith("data:image/png;base64,")


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
            "image_url": "https://example.com/product-image.png",
            "image_alt": "product alt",
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
