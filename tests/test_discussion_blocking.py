"""
Integration tests for discussion block/unblock endpoints using TestClient.
No external server required; relies on seeded test data via conftest.
"""

import pytest

pytestmark = pytest.mark.integration


def test_block_unblock_flow(auth_client, admin_client, test_product):
    # Create discussion as regular user
    create = auth_client.post(
        "/api/discussions",
        json={
            "content": "Test blockable post",
            "product_id": test_product["id"],
        },
    )
    assert create.status_code in (200, 201), create.text
    discussion = create.json()
    did = discussion["id"]

    # Block as admin
    block = admin_client.post(f"/api/discussions/{did}/block", json={"reason": "Spam"})
    assert block.status_code == 200, block.text
    blocked = block.json()
    assert blocked["blocked"] is True
    assert blocked["blocked_reason"] == "Spam"
    assert blocked["blocked_by"]

    # Unblock as admin
    unblock = admin_client.post(f"/api/discussions/{did}/unblock")
    assert unblock.status_code == 200, unblock.text
    unblocked = unblock.json()
    assert unblocked["blocked"] is False
    assert unblocked["blocked_by"] is None
    assert unblocked["blocked_reason"] is None


def test_user_cannot_block(auth_client, test_product):
    # Create discussion
    create = auth_client.post(
        "/api/discussions",
        json={
            "content": "User cannot block",
            "product_id": test_product["id"],
        },
    )
    assert create.status_code in (200, 201), create.text
    did = create.json()["id"]

    # Try to block as regular user
    block = auth_client.post(f"/api/discussions/{did}/block", json={"reason": "Nope"})
    assert block.status_code == 403, block.text


def test_user_cannot_unblock(auth_client, admin_client, test_product):
    # Create discussion and block as admin
    create = auth_client.post(
        "/api/discussions",
        json={
            "content": "Block then ensure user cannot unblock",
            "product_id": test_product["id"],
        },
    )
    assert create.status_code in (200, 201), create.text
    did = create.json()["id"]
    block = admin_client.post(f"/api/discussions/{did}/block", json={"reason": "Spam"})
    assert block.status_code == 200, block.text

    # Try to unblock as regular user
    unblock = auth_client.post(f"/api/discussions/{did}/unblock")
    assert unblock.status_code == 403, unblock.text
