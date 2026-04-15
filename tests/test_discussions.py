"""
Tests for discussion creation, threading, and retrieval.

Story 5.1: User Posts a New Discussion Thread
Story 5.2: User Replies to a Discussion Thread
"""

from datetime import datetime
from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.integration


def test_create_discussion_requires_auth(client: TestClient):
    """Test that creating a discussion requires authentication"""
    response = client.post(
        "/api/discussions",
        json={"product_id": "test-product", "content": "This is a test discussion"},
    )
    assert response.status_code == 401


def test_create_discussion_success(client: TestClient, auth_headers, test_user, test_product):
    """Test successful discussion creation"""
    response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={
            "product_id": test_product["id"],
            "content": "This is a great product! Does it work with X?",
        },
    )

    assert response.status_code == 201
    discussion = response.json()

    # Verify response structure
    assert "id" in discussion
    assert discussion["product_id"] == test_product["id"]
    assert discussion["content"] == "This is a great product! Does it work with X?"
    assert "user_id" in discussion
    assert "username" in discussion, "Backend must return username field"
    assert discussion["username"] is not None, "username should not be None"
    assert discussion["username"] == test_user["username"], (
        f"username should match user username, got {discussion['username']}"
    )
    assert "created_at" in discussion
    assert discussion.get("parent_id") is None  # Top-level discussion


def test_create_discussion_with_empty_content_fails(
    client: TestClient, auth_headers, test_user, test_product
):
    """Test that empty content is rejected"""
    response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": ""},
    )

    assert response.status_code == 422  # Validation error


def test_create_reply_to_discussion(client: TestClient, auth_headers, test_user, test_product):
    """Test creating a reply to an existing discussion (threading)"""
    # Create parent discussion
    parent_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "How do I install this?"},
    )
    assert parent_response.status_code == 201
    parent_id = parent_response.json()["id"]

    # Create reply
    reply_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={
            "product_id": test_product["id"],
            "content": "Check the documentation for installation steps.",
            "parent_id": parent_id,
        },
    )

    assert reply_response.status_code == 201
    reply = reply_response.json()

    assert reply["parent_id"] == parent_id
    assert reply["product_id"] == test_product["id"]
    assert "username" in reply
    assert reply["username"] is not None


def test_get_discussions_for_product(client: TestClient, auth_headers, test_user, test_product):
    """Test retrieving all discussions for a product"""
    # Create multiple discussions
    discussions_created = []
    for i in range(3):
        response = client.post(
            "/api/discussions",
            headers=auth_headers(test_user),
            json={"product_id": test_product["id"], "content": f"Discussion {i + 1}"},
        )
        assert response.status_code == 201
        discussions_created.append(response.json()["id"])

    # Retrieve discussions for product
    response = client.get(f"/api/discussions?product_id={test_product['id']}")
    assert response.status_code == 200

    discussions = response.json()
    assert len(discussions) >= 3  # At least our 3 discussions

    # Verify all have username field
    for discussion in discussions:
        assert "username" in discussion
        assert discussion["username"] is not None


def test_deep_nesting_replies(client: TestClient, auth_headers, test_user, test_product):
    """Test that replies can be nested multiple levels deep"""
    # Create parent
    parent_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Level 1"},
    )
    level1_id = parent_response.json()["id"]

    # Create level 2 reply
    level2_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Level 2", "parent_id": level1_id},
    )
    level2_id = level2_response.json()["id"]

    # Create level 3 reply
    level3_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Level 3", "parent_id": level2_id},
    )

    assert level3_response.status_code == 201
    level3 = level3_response.json()
    assert level3["parent_id"] == level2_id
    assert "username" in level3


def test_user_can_reply_to_own_discussion(
    client: TestClient, auth_headers, test_user, test_product
):
    """Test that a user can reply to their own discussion"""
    # Create discussion
    parent_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "I have a question"},
    )
    parent_id = parent_response.json()["id"]

    # Reply to own discussion
    reply_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={
            "product_id": test_product["id"],
            "content": "Never mind, I figured it out!",
            "parent_id": parent_id,
        },
    )

    assert reply_response.status_code == 201
    assert reply_response.json()["parent_id"] == parent_id


def test_discussion_timestamps_are_valid(client: TestClient, auth_headers, test_user, test_product):
    """Test that discussion timestamps are properly formatted"""
    response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Test timestamp"},
    )

    assert response.status_code == 201
    discussion = response.json()

    # Verify created_at is a valid datetime string
    assert "created_at" in discussion
    created_at = discussion["created_at"]
    # Should be able to parse as ISO datetime
    datetime.fromisoformat(created_at.replace("Z", "+00:00"))


def test_get_discussions_without_filters(client: TestClient, auth_headers, test_user, test_product):
    """Test getting discussions without filters returns all recent discussions"""
    # Create discussion
    client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Test discussion"},
    )

    # Get all discussions
    response = client.get("/api/discussions")
    assert response.status_code == 200
    discussions = response.json()
    assert isinstance(discussions, list)
    assert len(discussions) > 0

    # All should have username
    for discussion in discussions:
        assert "username" in discussion


def test_filter_discussions_by_parent_id(client: TestClient, auth_headers, test_user, test_product):
    """Test filtering discussions by parent_id to get replies"""
    # Create parent
    parent_response = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={"product_id": test_product["id"], "content": "Parent discussion"},
    )
    parent_id = parent_response.json()["id"]

    # Create multiple replies
    for i in range(2):
        client.post(
            "/api/discussions",
            headers=auth_headers(test_user),
            json={
                "product_id": test_product["id"],
                "content": f"Reply {i + 1}",
                "parent_id": parent_id,
            },
        )

    # Get replies only
    response = client.get(f"/api/discussions?parent_id={parent_id}")
    assert response.status_code == 200

    replies = response.json()
    assert len(replies) == 2
    for reply in replies:
        assert reply["parent_id"] == parent_id
        assert "username" in reply


def test_delete_discussion_with_invalid_id_returns_422(client: TestClient, auth_headers, test_user):
    """Invalid UUID path params should be rejected at API validation layer."""
    response = client.delete(
        "/api/discussions/not-a-uuid",
        headers=auth_headers(test_user),
    )
    assert response.status_code == 422


def test_get_single_discussion_success(client: TestClient, auth_headers, test_user, test_product):
    """A created discussion should be retrievable by id."""
    create = client.post(
        "/api/discussions",
        headers=auth_headers(test_user),
        json={
            "product_id": test_product["id"],
            "content": "Single fetch test",
        },
    )
    assert create.status_code == 201
    discussion_id = create.json()["id"]

    get_resp = client.get(f"/api/discussions/{discussion_id}")
    assert get_resp.status_code == 200
    discussion = get_resp.json()
    assert discussion["id"] == discussion_id
    assert discussion["content"] == "Single fetch test"


def test_get_single_discussion_not_found(client: TestClient):
    """Fetching a non-existent discussion should return 404."""
    response = client.get("/api/discussions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_update_discussion_success(auth_client, test_product):
    """Owner can edit discussion content."""
    create = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Original content",
        },
    )
    assert create.status_code == 201, create.text
    discussion_id = create.json()["id"]

    update = auth_client.put(
        f"/api/discussions/{discussion_id}",
        json={"content": "Edited content"},
    )
    assert update.status_code == 200, update.text
    updated = update.json()
    assert updated["id"] == discussion_id
    assert updated["content"] == "Edited content"


def test_update_discussion_forbidden_for_non_owner(auth_client, auth_client_2, test_product):
    """Non-owner cannot edit someone else's discussion."""
    create = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Owner content",
        },
    )
    assert create.status_code == 201, create.text
    discussion_id = create.json()["id"]

    update = auth_client_2.put(
        f"/api/discussions/{discussion_id}",
        json={"content": "Unauthorized edit"},
    )
    assert update.status_code == 403, update.text


def test_update_discussion_not_found(auth_client):
    """Editing a non-existent discussion should return 404."""
    response = auth_client.put(
        "/api/discussions/00000000-0000-0000-0000-000000000000",
        json={"content": "No record"},
    )
    assert response.status_code == 404


def test_delete_discussion_soft_delete_success(auth_client, test_product):
    """Deleting a leaf discussion hides it (404 on GET, absent from list)."""
    create = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Delete me",
        },
    )
    assert create.status_code == 201, create.text
    discussion_id = create.json()["id"]

    delete_resp = auth_client.delete(f"/api/discussions/{discussion_id}")
    assert delete_resp.status_code == 200, delete_resp.text
    assert delete_resp.json()["content"] == "[deleted]"

    # Leaf deleted post is no longer visible
    get_resp = auth_client.get(f"/api/discussions/{discussion_id}")
    assert get_resp.status_code == 404, get_resp.text

    # Also absent from list
    list_resp = auth_client.get(f"/api/discussions?product_id={test_product['id']}")
    ids = [d["id"] for d in list_resp.json()]
    assert discussion_id not in ids


def test_delete_discussion_with_replies_stays_visible(auth_client, auth_client_2, test_product):
    """Deleting a discussion that has replies keeps it visible as [deleted]."""
    parent = auth_client.post(
        "/api/discussions",
        json={"product_id": test_product["id"], "content": "Parent post"},
    )
    assert parent.status_code == 201
    parent_id = parent.json()["id"]

    reply = auth_client_2.post(
        "/api/discussions",
        json={"product_id": test_product["id"], "content": "A reply", "parent_id": parent_id},
    )
    assert reply.status_code == 201

    auth_client.delete(f"/api/discussions/{parent_id}")

    get_resp = auth_client.get(f"/api/discussions/{parent_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["content"] == "[deleted]"


def test_delete_discussion_forbidden_for_non_owner(auth_client, auth_client_2, test_product):
    """Non-owner cannot delete someone else's discussion."""
    create = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Only owner can delete",
        },
    )
    assert create.status_code == 201, create.text
    discussion_id = create.json()["id"]

    delete_resp = auth_client_2.delete(f"/api/discussions/{discussion_id}")
    assert delete_resp.status_code == 403, delete_resp.text


def test_delete_discussion_not_found(auth_client):
    """Deleting a non-existent discussion should return 404."""
    response = auth_client.delete("/api/discussions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_discussion_allowed_for_admin(auth_client, admin_client, test_product):
    """Admin can delete discussions created by another user."""
    create = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Admin can delete this",
        },
    )
    assert create.status_code == 201, create.text
    discussion_id = create.json()["id"]

    delete_resp = admin_client.delete(f"/api/discussions/{discussion_id}")
    assert delete_resp.status_code == 200, delete_resp.text
    assert delete_resp.json()["content"] == "[deleted]"
