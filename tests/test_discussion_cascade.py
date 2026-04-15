"""
Integration tests for cascade block/unblock on discussion threads.
Uses TestClient and seeded fixtures; no mocks, no external server.
"""

import pytest

pytestmark = pytest.mark.integration


def test_block_cascades_to_descendants(auth_client, admin_client, test_product):
    # Create a hierarchy: parent -> (reply1 -> reply1child), (reply2)
    parent = auth_client.post(
        "/api/discussions",
        json={
            "content": "Parent post",
            "product_id": test_product["id"],
        },
    )
    assert parent.status_code in (200, 201), parent.text
    parent_id = parent.json()["id"]

    reply1 = auth_client.post(
        "/api/discussions",
        json={
            "content": "Reply 1",
            "product_id": test_product["id"],
            "parent_id": parent_id,
        },
    )
    assert reply1.status_code in (200, 201), reply1.text
    reply1_id = reply1.json()["id"]

    reply2 = auth_client.post(
        "/api/discussions",
        json={
            "content": "Reply 2",
            "product_id": test_product["id"],
            "parent_id": parent_id,
        },
    )
    assert reply2.status_code in (200, 201), reply2.text
    reply2_id = reply2.json()["id"]

    reply1child = auth_client.post(
        "/api/discussions",
        json={
            "content": "Reply 1 child",
            "product_id": test_product["id"],
            "parent_id": reply1_id,
        },
    )
    assert reply1child.status_code in (200, 201), reply1child.text
    reply1child_id = reply1child.json()["id"]

    # Block parent as admin; should cascade
    block = admin_client.post(f"/api/discussions/{parent_id}/block", json={"reason": "spam"})
    assert block.status_code == 200, block.text

    # Verify all are blocked
    for did in (parent_id, reply1_id, reply2_id, reply1child_id):
        r = auth_client.get(f"/api/discussions/{did}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["blocked"] is True
        assert data["blocked_reason"] == "spam"


def test_unblock_cascades_to_descendants(auth_client, admin_client, test_product):
    # Create simple chain: parent -> child
    parent = auth_client.post(
        "/api/discussions",
        json={
            "content": "Parent to unblock",
            "product_id": test_product["id"],
        },
    )
    assert parent.status_code in (200, 201), parent.text
    parent_id = parent.json()["id"]

    child = auth_client.post(
        "/api/discussions",
        json={
            "content": "Child",
            "product_id": test_product["id"],
            "parent_id": parent_id,
        },
    )
    assert child.status_code in (200, 201), child.text
    child_id = child.json()["id"]

    # Block then unblock parent
    block = admin_client.post(f"/api/discussions/{parent_id}/block", json={"reason": "spam"})
    assert block.status_code == 200, block.text
    unblock = admin_client.post(f"/api/discussions/{parent_id}/unblock")
    assert unblock.status_code == 200, unblock.text

    # Verify both are unblocked
    for did in (parent_id, child_id):
        r = auth_client.get(f"/api/discussions/{did}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["blocked"] is False
        assert data["blocked_by"] is None
        assert data["blocked_reason"] is None
        assert data["blocked_at"] is None
