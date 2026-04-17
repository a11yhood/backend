from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.integration


def _assert_full_iso_timestamp(value: str | None):
    assert value is not None
    assert isinstance(value, str)
    assert "T" in value
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_user_endpoints_return_full_iso_timestamps(client, admin_client, clean_database, test_user):
    response = client.get(f"/api/users/{test_user['id']}")

    assert response.status_code == 200
    user = response.json()
    _assert_full_iso_timestamp(user["created_at"])
    _assert_full_iso_timestamp(user["joined_at"])
    _assert_full_iso_timestamp(user["last_active"])

    admin_list = admin_client.get("/api/users/")
    assert admin_list.status_code == 200
    listed_user = next(row for row in admin_list.json() if row["id"] == test_user["id"])
    _assert_full_iso_timestamp(listed_user["created_at"])


def test_request_endpoints_return_full_iso_timestamps(client, clean_database, test_user, auth_headers):
    create = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Need moderation access"},
        headers=auth_headers(test_user),
    )

    assert create.status_code == 201
    created_request = create.json()
    _assert_full_iso_timestamp(created_request["created_at"])
    _assert_full_iso_timestamp(created_request["updated_at"])

    mine = client.get(f"/api/users/{test_user['username']}/requests", headers=auth_headers(test_user))
    assert mine.status_code == 200
    listed_request = next(row for row in mine.json() if row["id"] == created_request["id"])
    _assert_full_iso_timestamp(listed_request["created_at"])
    _assert_full_iso_timestamp(listed_request["updated_at"])


def test_activity_endpoints_return_full_iso_timestamps(
    auth_client,
    clean_database,
    test_user,
    test_product,
):
    create = auth_client.post(
        "/api/activities",
        json={
            "user_id": test_user["id"],
            "type": "rating",
            "product_id": test_product["id"],
            "timestamp": "2026-04-16",
            "metadata": {"rating": 5},
        },
    )

    assert create.status_code == 201
    activity = create.json()
    _assert_full_iso_timestamp(activity["timestamp"])
    _assert_full_iso_timestamp(activity["created_at"])

    detail = auth_client.get(f"/api/activities/{activity['id']}")
    assert detail.status_code == 200
    _assert_full_iso_timestamp(detail.json()["timestamp"])


def test_blog_post_endpoints_return_full_iso_timestamps(admin_client, clean_database, test_admin):
    slug = f"timestamp-blog-{int(datetime.now(UTC).timestamp() * 1000)}"
    create = admin_client.post(
        "/api/blog-posts",
        json={
            "title": "Timestamp Serialization",
            "slug": slug,
            "content": "Body",
            "excerpt": "Excerpt",
            "header_image_alt": "Alt text",
            "tags": ["timestamps"],
            "featured": False,
            "published": True,
            "publish_date": "2026-04-16",
            "author_id": test_admin["id"],
            "author_name": test_admin["username"],
        },
    )

    assert create.status_code == 201
    post = create.json()
    _assert_full_iso_timestamp(post["created_at"])
    _assert_full_iso_timestamp(post["updated_at"])
    _assert_full_iso_timestamp(post["publish_date"])

    detail = admin_client._base.get(f"/api/blog-posts/slug/{slug}")
    assert detail.status_code == 200
    _assert_full_iso_timestamp(detail.json()["publish_date"])
