"""
Integration tests for user request workflows.

Tests the user experience for:
- Requesting moderator status
- Requesting product management
- Editing products (as a manager)
- Admin approval/rejection of requests
"""

from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


def test_user_can_request_moderator_status(client, test_user, auth_headers):
    """Test that a regular user can request moderator status"""
    # Create moderator request
    response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help moderate the community"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "moderator"
    assert data["status"] == "pending"
    assert data["user_id"] == test_user["id"]
    assert data["reason"] == "I want to help moderate the community"


def test_user_can_request_admin_status(client, test_user, auth_headers):
    """Test that a user can request admin status"""
    response = client.post(
        "/api/requests/",
        json={"type": "admin", "reason": "I am a core contributor"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "admin"
    assert data["status"] == "pending"


def test_user_can_request_product_editor(client, test_user, test_product, auth_headers):
    """Test that a user can request ownership of a product"""
    response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I am the creator of this product",
        },
        headers=auth_headers(test_user),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "product-ownership"
    assert data["status"] == "pending"
    assert data["product_id"] == test_product["id"]
    assert data["reason"] == "I am the creator of this product"


def test_product_management_request_requires_product_id(client, test_user, auth_headers):
    """Test that product management requests must include a product_id"""
    response = client.post(
        "/api/requests/",
        json={"type": "product-ownership", "reason": "I am the creator"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 400
    assert "product_id" in response.json()["detail"].lower()


def test_cannot_create_duplicate_pending_request(client, test_user, auth_headers):
    """Test that users cannot create duplicate pending requests"""
    # Create first request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "First request"},
        headers=auth_headers(test_user),
    )

    # Try to create second request
    response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Second request"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 400
    assert "pending" in response.json()["detail"].lower()


def test_user_can_see_own_requests(client, test_user, test_user_2, auth_headers):
    """Test that users can see their own requests but not others'"""
    # User 1 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 1 request"},
        headers=auth_headers(test_user),
    )

    # User 2 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 2 request"},
        headers=auth_headers(test_user_2),
    )

    # User 1 lists their requests
    response = client.get("/api/requests/", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == test_user["id"]


def test_admin_can_see_all_requests(client, test_user, test_user_2, test_admin, auth_headers):
    """Test that admins can see all requests"""
    # User 1 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 1 request"},
        headers=auth_headers(test_user),
    )

    # User 2 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 2 request"},
        headers=auth_headers(test_user_2),
    )

    # Admin lists all requests
    response = client.get("/api/requests/", headers=auth_headers(test_admin))

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2  # At least the two we created


def test_moderator_can_see_all_requests(
    client, test_user, test_user_2, test_moderator, auth_headers
):
    """Test that moderators can see all requests"""
    # User 1 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 1 request"},
        headers=auth_headers(test_user),
    )

    # User 2 creates a request
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "User 2 request"},
        headers=auth_headers(test_user_2),
    )

    # Moderator lists all requests
    response = client.get("/api/requests/", headers=auth_headers(test_moderator))

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2  # At least the two we created


def test_moderator_can_approve_ownership_request(
    client, test_user, test_product, test_moderator, auth_headers
):
    """Test that moderators can approve ownership requests"""
    # User creates ownership request
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this product",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Moderator approves the request
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_moderator),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == test_moderator["id"]
    assert data["reviewed_at"] is not None


def test_moderator_can_reject_request(client, test_user, test_moderator, auth_headers):
    """Test that moderators can reject requests"""
    # User creates request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Moderator rejects the request
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "rejected"},
        headers=auth_headers(test_moderator),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reviewed_by"] == test_moderator["id"]


def test_admin_can_approve_moderator_request(
    client, test_user, test_admin, auth_headers, sqlite_db
):
    """Test that admin can approve a moderator request"""
    # User creates moderator request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Admin approves the request
    response = client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    if response.status_code != 200:
        print(f"Error: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == test_admin["id"]
    assert data["reviewed_at"] is not None


def test_admin_can_reject_request(client, test_user, test_admin, auth_headers):
    """Test that admin can reject a request"""
    # User creates request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Admin rejects the request
    response = client.patch(
        f"/api/requests/{request_id}", json={"status": "rejected"}, headers=auth_headers(test_admin)
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reviewed_by"] == test_admin["id"]


def test_non_admin_cannot_approve_request(client, test_user, test_user_2, auth_headers):
    """Test that regular users cannot approve requests"""
    # User 1 creates request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # User 2 tries to approve
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_user_2),
    )

    assert response.status_code == 403


def test_user_cannot_approve_own_request(client, test_user, auth_headers):
    """Test that users cannot approve their own requests"""
    # User creates request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # User tries to approve their own request
    response = client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_user)
    )

    assert response.status_code == 403


def test_approved_product_management_grants_access(
    client, test_user, test_product, test_admin, auth_headers, sqlite_db
):
    """Test that approving a product management request grants management access"""
    # User requests ownership
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this product",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Admin approves
    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Verify user is now a manager by checking product_editors table
    editors_response = (
        sqlite_db.table("product_editors")
        .select("*")
        .eq("product_id", test_product["id"])
        .eq("user_id", test_user["id"])
        .execute()
    )

    assert len(editors_response.data) == 1


def test_admin_promotes_user_to_moderator_and_admin(
    client, test_user, test_admin, auth_headers, sqlite_db
):
    """Admin can approve role requests to promote a user to moderator, then to admin (real DB writes)."""
    # User requests moderator role
    create_mod = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Helping moderate content"},
        headers=auth_headers(test_user),
    )
    mod_request_id = create_mod.json()["id"]

    # Admin approves moderator request
    approve_mod = client.patch(
        f"/api/requests/{mod_request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )
    assert approve_mod.status_code == 200

    # Verify role updated to moderator in DB
    mod_role = sqlite_db.table("users").select("role").eq("id", test_user["id"]).execute()
    assert mod_role.data[0]["role"] == "moderator"

    # User requests admin role after becoming moderator
    create_admin = client.post(
        "/api/requests/",
        json={"type": "admin", "reason": "Escalating responsibilities"},
        headers=auth_headers({**test_user, "role": "moderator"}),
    )
    admin_request_id = create_admin.json()["id"]

    # Admin approves admin request
    approve_admin = client.patch(
        f"/api/requests/{admin_request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )
    assert approve_admin.status_code == 200

    # Verify role updated to admin in DB
    admin_role = sqlite_db.table("users").select("role").eq("id", test_user["id"]).execute()
    assert admin_role.data[0]["role"] == "admin"


def test_admin_approval_adds_product_owner_and_lists(
    client, test_user, test_product, test_admin, auth_headers
):
    """Admin approval of ownership request inserts product_editors row and surfaces via owners endpoint."""
    create_request = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Need edit access",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_request.json()["id"]

    approve = client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )
    assert approve.status_code == 200

    owners = client.get(f"/api/products/{test_product['id']}/owners")
    assert owners.status_code == 200
    editor_ids = [owner["id"] for owner in owners.json()]
    assert test_user["id"] in editor_ids


def test_product_manager_can_edit_product(
    client, test_user, test_product, test_admin, auth_headers, sqlite_db
):
    """Test that product managers can edit their products"""
    # Grant management first
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this product",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Now manager can edit the product
    response = client.patch(
        f"/api/products/{test_product['id']}",
        json={"name": "Updated Product Name", "description": "Updated description"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Product Name"
    assert data["description"] == "Updated description"


def test_non_owner_cannot_edit_product(client, test_user_2, test_product, auth_headers):
    """Test that non-owners cannot edit products"""
    response = client.patch(
        f"/api/products/{test_product['id']}",
        json={"name": "Hacked Name", "description": "Hacked description"},
        headers=auth_headers(test_user_2),
    )

    # Should be forbidden since user is not an owner or admin
    assert response.status_code in [403, 401]


def test_user_can_delete_own_pending_request(client, test_user, auth_headers):
    """Test that users can delete their own pending requests"""
    # Create request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Delete the request
    response = client.delete(f"/api/requests/{request_id}", headers=auth_headers(test_user))

    assert response.status_code == 200

    # Verify it's deleted
    response = client.get("/api/requests/", headers=auth_headers(test_user))
    assert len(response.json()) == 0


def test_user_cannot_delete_approved_request(client, test_user, test_admin, auth_headers):
    """Test that users cannot delete approved requests"""
    # Create and approve request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "I want to help"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Try to delete
    response = client.delete(f"/api/requests/{request_id}", headers=auth_headers(test_user))

    assert response.status_code == 403


def test_filter_requests_by_status(client, test_user, test_admin, auth_headers):
    """Test filtering requests by status"""
    # Create two requests
    response1 = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Request 1"},
        headers=auth_headers(test_user),
    )
    request_id = response1.json()["id"]

    client.post(
        "/api/requests/",
        json={"type": "admin", "reason": "Request 2"},
        headers=auth_headers(test_user),
    )

    # Approve one
    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Filter by pending
    response = client.get("/api/requests/?status=pending", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"


def test_filter_requests_by_type(client, test_user, test_product, auth_headers):
    """Test filtering requests by type"""
    # Create different types of requests
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Moderator request"},
        headers=auth_headers(test_user),
    )

    client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Ownership request",
        },
        headers=auth_headers(test_user),
    )

    # Filter by type
    response = client.get("/api/requests/?type=moderator", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "moderator"


def test_invalid_request_type_rejected(client, test_user, auth_headers):
    """Test that invalid request types are rejected"""
    response = client.post(
        "/api/requests/",
        json={"type": "invalid-type", "reason": "Test"},
        headers=auth_headers(test_user),
    )

    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_invalid_status_update_rejected(client, test_user, test_admin, auth_headers):
    """Test that invalid status updates are rejected"""
    # Create request
    create_response = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Test"},
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # Try invalid status
    response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "invalid-status"},
        headers=auth_headers(test_admin),
    )

    assert response.status_code == 400


def test_multiple_product_editor_requests_allowed(
    client, test_user, test_product, auth_headers, sqlite_db
):
    """Test that users can request ownership of multiple products"""
    # Create a second product
    product2 = (
        sqlite_db.table("products")
        .insert(
            {
                "name": "Second Product",
                "description": "Another product",
                "source": "github",
                "type": "Other",
                "url": "https://github.com/example/product-2",
                "slug": f"second-product-{datetime.now().timestamp():.0f}",
            }
        )
        .execute()
        .data[0]
    )

    # Request ownership of first product
    response1 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this",
        },
        headers=auth_headers(test_user),
    )

    # Request ownership of second product
    response2 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": product2["id"],
            "reason": "I created this too",
        },
        headers=auth_headers(test_user),
    )

    assert response1.status_code == 201
    assert response2.status_code == 201


def test_cannot_duplicate_ownership_request_for_same_product(
    client, test_user, test_product, auth_headers
):
    """Test that users cannot create duplicate ownership requests for the same product"""
    # Create first request
    client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "First request",
        },
        headers=auth_headers(test_user),
    )

    # Try to create duplicate
    response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Second request",
        },
        headers=auth_headers(test_user),
    )

    assert response.status_code == 400
    assert "pending" in response.json()["detail"].lower()


def test_user_dashboard_shows_own_requests(client, test_user, test_product, auth_headers):
    """Test that users can view their own requests via /me endpoint"""
    # Create multiple requests
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Want to moderate"},
        headers=auth_headers(test_user),
    )

    client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this",
        },
        headers=auth_headers(test_user),
    )

    # Get user's dashboard
    response = client.get("/api/requests/me", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(req["user_id"] == test_user["id"] for req in data)


def test_user_dashboard_filter_by_status(client, test_user, test_admin, auth_headers):
    """Test filtering user's own requests by status"""
    # Create two requests
    response1 = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Request 1"},
        headers=auth_headers(test_user),
    )
    request_id = response1.json()["id"]

    client.post(
        "/api/requests/",
        json={"type": "admin", "reason": "Request 2"},
        headers=auth_headers(test_user),
    )

    # Approve one
    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Filter by pending on dashboard
    response = client.get("/api/requests/me?status=pending", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"

    # Filter by approved
    response = client.get("/api/requests/me?status=approved", headers=auth_headers(test_user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "approved"


def test_user_dashboard_filter_by_type(client, test_user, test_product, auth_headers):
    """Test filtering user's own requests by type"""
    # Create different types of requests
    client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "Moderator request"},
        headers=auth_headers(test_user),
    )

    client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Ownership request",
        },
        headers=auth_headers(test_user),
    )

    # Filter by type
    response = client.get(
        "/api/requests/me?type=product-ownership", headers=auth_headers(test_user)
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "product-ownership"
    assert data[0]["product_id"] == test_product["id"]


def test_user_can_cancel_pending_ownership_request(client, test_user, test_product, auth_headers):
    """Test that users can cancel their pending ownership requests"""
    # Create ownership request
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I want ownership",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    # User cancels the request
    response = client.delete(f"/api/requests/{request_id}", headers=auth_headers(test_user))

    assert response.status_code == 200

    # Verify it's deleted from dashboard
    response = client.get("/api/requests/me", headers=auth_headers(test_user))
    assert len(response.json()) == 0


def test_user_cannot_cancel_approved_ownership_request(
    client, test_user, test_product, test_admin, auth_headers
):
    """Test that users cannot cancel approved ownership requests"""
    # Create and approve ownership request
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this",
        },
        headers=auth_headers(test_user),
    )
    request_id = create_response.json()["id"]

    client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}, headers=auth_headers(test_admin)
    )

    # Try to delete
    response = client.delete(f"/api/requests/{request_id}", headers=auth_headers(test_user))

    assert response.status_code == 403


def test_multiple_users_can_own_same_product(
    client, test_user, test_user_2, test_product, test_admin, auth_headers, sqlite_db
):
    """Test that multiple users can be granted ownership of the same product"""
    # User 1 requests ownership
    create_response_1 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I am a co-creator",
        },
        headers=auth_headers(test_user),
    )
    request_id_1 = create_response_1.json()["id"]

    # User 2 requests ownership
    create_response_2 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I am also a co-creator",
        },
        headers=auth_headers(test_user_2),
    )
    request_id_2 = create_response_2.json()["id"]

    # Admin approves both requests
    client.patch(
        f"/api/requests/{request_id_1}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    client.patch(
        f"/api/requests/{request_id_2}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    # Verify both users are now editors
    editors_response = (
        sqlite_db.table("product_editors")
        .select("*")
        .eq("product_id", test_product["id"])
        .execute()
    )

    assert len(editors_response.data) == 2
    editor_user_ids = [editor["user_id"] for editor in editors_response.data]
    assert test_user["id"] in editor_user_ids
    assert test_user_2["id"] in editor_user_ids


def test_multiple_owners_can_all_edit_product(
    client, test_user, test_user_2, test_product, test_admin, auth_headers, sqlite_db
):
    """Test that all owners of a product can edit it"""
    # Grant ownership to both users
    create_response_1 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Co-creator",
        },
        headers=auth_headers(test_user),
    )
    request_id_1 = create_response_1.json()["id"]

    create_response_2 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Co-creator",
        },
        headers=auth_headers(test_user_2),
    )
    request_id_2 = create_response_2.json()["id"]

    # Admin approves both
    client.patch(
        f"/api/requests/{request_id_1}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    client.patch(
        f"/api/requests/{request_id_2}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    # Both users can edit the product
    response1 = client.patch(
        f"/api/products/{test_product['id']}",
        json={"name": "Updated by User 1"},
        headers=auth_headers(test_user),
    )
    assert response1.status_code == 200

    response2 = client.patch(
        f"/api/products/{test_product['id']}",
        json={"name": "Updated by User 2"},
        headers=auth_headers(test_user_2),
    )
    assert response2.status_code == 200


def test_get_all_owners_of_product(
    client, test_user, test_user_2, test_product, test_admin, auth_headers
):
    """Test retrieving all owners of a product"""
    # Grant ownership to both users
    create_response_1 = client.post(
        "/api/requests/",
        json={"type": "product-ownership", "product_id": test_product["id"], "reason": "Creator"},
        headers=auth_headers(test_user),
    )
    request_id_1 = create_response_1.json()["id"]

    create_response_2 = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Co-creator",
        },
        headers=auth_headers(test_user_2),
    )
    request_id_2 = create_response_2.json()["id"]

    # Admin approves both
    client.patch(
        f"/api/requests/{request_id_1}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    client.patch(
        f"/api/requests/{request_id_2}",
        json={"status": "approved"},
        headers=auth_headers(test_admin),
    )

    # Get owners list
    response = client.get(f"/api/products/{test_product['id']}/owners")

    assert response.status_code == 200
    owners = response.json()
    assert len(owners) == 2
    editor_ids = [owner["id"] for owner in owners]
    assert test_user["id"] in editor_ids
    assert test_user_2["id"] in editor_ids


def test_ownership_request_workflow_complete(
    client, test_user, test_product, test_moderator, auth_headers, sqlite_db
):
    """Test complete workflow: request -> moderator sees it -> approves -> user sees status -> user gains edit access"""
    # Step 1: User requests ownership
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "I created this product",
        },
        headers=auth_headers(test_user),
    )

    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    # Step 2: User can see their pending request on dashboard
    dashboard_response = client.get("/api/requests/me", headers=auth_headers(test_user))

    assert dashboard_response.status_code == 200
    user_requests = dashboard_response.json()
    assert len(user_requests) == 1
    assert user_requests[0]["status"] == "pending"
    assert user_requests[0]["product_id"] == test_product["id"]

    # Step 3: Moderator can see all pending requests
    moderator_response = client.get(
        "/api/requests/?status=pending", headers=auth_headers(test_moderator)
    )

    assert moderator_response.status_code == 200
    moderator_requests = moderator_response.json()
    assert len(moderator_requests) >= 1
    assert any(req["id"] == request_id for req in moderator_requests)

    # Step 4: Moderator approves the request
    approve_response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_moderator),
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    # Step 5: User sees the approved status
    updated_dashboard = client.get("/api/requests/me", headers=auth_headers(test_user))

    assert updated_dashboard.json()[0]["status"] == "approved"

    # Step 6: User can now edit the product
    edit_response = client.patch(
        f"/api/products/{test_product['id']}",
        json={"name": "Updated Product Name"},
        headers=auth_headers(test_user),
    )

    assert edit_response.status_code == 200
    assert edit_response.json()["name"] == "Updated Product Name"


def test_product_management_request_updates_managers_and_owned_products(
    client, test_user, test_product, test_moderator, auth_headers, sqlite_db
):
    """User requests product management, moderator approves, user becomes an owner and sees it in owned-products."""
    # User submits a management request
    create_response = client.post(
        "/api/requests/",
        json={
            "type": "product-ownership",
            "product_id": test_product["id"],
            "reason": "Need to maintain this listing",
        },
        headers=auth_headers(test_user),
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    # Moderator approves the request (manager perspective)
    approve_response = client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
        headers=auth_headers(test_moderator),
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    # Moderator can see the request in the approved list
    approved_list = client.get(
        "/api/requests/?status=approved",
        headers=auth_headers(test_moderator),
    )
    assert approved_list.status_code == 200
    assert any(req["id"] == request_id for req in approved_list.json())

    # User perspective: owners endpoint now lists the user
    owners_response = client.get(
        f"/api/products/{test_product['id']}/owners",
        headers=auth_headers(test_user),
    )
    assert owners_response.status_code == 200
    owners = owners_response.json()
    assert any(owner["id"] == test_user["id"] for owner in owners)

    # User perspective: owned-products endpoint includes the product
    owned_products_response = client.get(
        f"/api/users/{test_user['id']}/owned-products",
        headers=auth_headers(test_user),
    )
    assert owned_products_response.status_code == 200
    owned_products = owned_products_response.json().get("products", [])
    assert any(p["id"] == test_product["id"] for p in owned_products)
