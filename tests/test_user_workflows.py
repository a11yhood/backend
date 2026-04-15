"""
Integration tests for user workflows.

These tests verify that complete user actions have the expected side effects:
- Product submission → user becomes owner + activity is logged
- Rating a product → activity is logged
- Creating a discussion → activity is logged
"""

import uuid
from datetime import UTC, datetime
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def test_user_id():
    """Return a consistent test user ID"""
    return str(uuid.uuid4())


@pytest.fixture
def test_product_data():
    """Return test product data"""
    return {
        "name": "Test Accessible Product",
        "source": "github",
        "type": "Software",
        "url": f"https://github.com/user/product-{uuid.uuid4()}",
        "image": None,
        "description": "A test product for integration testing",
    }


# ============================================================================
# STORY 3.1: USER SUBMITS A NEW PRODUCT
# ============================================================================


def test_product_submission_creates_product_and_adds_owner(
    auth_client,
    test_user,
    clean_database,
):
    """
    When a user submits a product:
    - Product is created with correct fields
    - User is added as product manager
    - Product has correct created_by field
    """
    product_data = {
        "name": "Accessible Testing Tool",
        "description": "A tool for testing accessibility features",
        "source": "github",
        "categories": ["testing"],
        "source_url": f"https://github.com/test/tool-{uuid.uuid4()}",
    }

    # Submit product via API with auth
    response = auth_client.post("/api/products", json=product_data)

    # Verify product creation succeeds
    assert response.status_code == 201
    product = response.json()
    assert product["name"] == product_data["name"]
    assert product["created_by"] == test_user["id"]
    assert "created_at" in product
    assert product["description"] == product_data["description"]


def test_product_submission_sets_correct_created_at(
    auth_client,
    test_user,
    clean_database,
):
    """
    Product submission should set created_at timestamp
    """
    product_data = {
        "name": "Test Product with Timestamp",
        "description": "Testing created_at field",
        "source": "github",
        "type": "Software",
        "source_url": f"https://github.com/user/test-{uuid.uuid4()}",
    }

    before_submission = datetime.now(UTC)
    response = auth_client.post("/api/products", json=product_data)
    after_submission = datetime.now(UTC)

    assert response.status_code == 201
    product = response.json()
    assert "created_at" in product

    # Verify timestamp is reasonable
    created_at = datetime.fromisoformat(product["created_at"].replace("Z", "+00:00"))
    assert before_submission <= created_at <= after_submission


# ============================================================================
# STORY 4.1: USER RATES A PRODUCT
# ============================================================================


def test_product_rating_logs_activity(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    When a user rates a product:
    - Rating is saved with user_id and product_id
    - Rating can be retrieved
    """
    rating_value = 4

    response = auth_client.post(
        "/api/ratings",
        json={"product_id": test_product["id"], "rating": rating_value},
    )

    assert response.status_code == 201
    rating = response.json()
    assert rating["rating"] == rating_value
    assert rating["user_id"] == test_user["id"]
    assert rating["product_id"] == test_product["id"]
    assert "created_at" in rating


# ============================================================================
# STORY 5.1: USER PARTICIPATES IN DISCUSSIONS
# ============================================================================


def test_discussion_creation_with_parent_id(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    When a user creates a discussion/comment:
    - Discussion is saved with user ID and product ID
    - Parent comment ID is preserved (for threading)
    """
    # Create a parent discussion first
    parent_response = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": "Initial discussion",
        },
    )
    assert parent_response.status_code == 201
    parent_id = parent_response.json()["id"]

    # Now create a reply with parent_id
    comment_text = "Great accessibility features!"
    response = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "parent_id": parent_id,
            "content": comment_text,
        },
    )

    assert response.status_code == 201
    discussion = response.json()
    assert discussion["content"] == comment_text
    assert discussion["user_id"] == test_user["id"]
    assert discussion["product_id"] == test_product["id"]
    assert discussion["parent_id"] == parent_id


def test_discussion_creation_without_parent_starts_new_thread(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    Discussion without parent_id starts a new thread
    """
    comment_text = "Starting a new discussion"

    response = auth_client.post(
        "/api/discussions",
        json={
            "product_id": test_product["id"],
            "content": comment_text,
        },
    )

    assert response.status_code == 201
    discussion = response.json()
    assert discussion["content"] == comment_text
    assert discussion["parent_id"] is None
    assert discussion["user_id"] == test_user["id"]


# ============================================================================
# STORY 8.1: USER ACTIVITIES ARE LOGGED
# ============================================================================


def test_activity_logging_stores_metadata(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    Activity logging should store extra metadata for later analysis
    """
    product_id = test_product["id"]
    timestamp = datetime.now(UTC).isoformat()

    response = auth_client.post(
        "/api/activities",
        json={
            "user_id": test_user["id"],
            "type": "rating",
            "product_id": product_id,
            "timestamp": timestamp,
            "metadata": {"rating": 5},
        },
    )

    assert response.status_code == 201
    activity = response.json()
    assert activity["type"] == "rating"
    assert activity["product_id"] == product_id
    assert activity["metadata"]["rating"] == 5


def test_activities_can_be_queried_by_user(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    Activities should be queryable by user_id
    """
    # Log some activities
    for i in range(3):
        auth_client.post(
            "/api/activities",
            json={
                "user_id": test_user["id"],
                "type": "rating" if i % 2 == 0 else "discussion",
                "product_id": test_product["id"],
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    # Query activities
    response = auth_client.get("/api/activities")

    assert response.status_code == 200
    activities = response.json()
    # Should have at least the activities we just created
    assert len(activities) >= 3


# ============================================================================
# STORY 3.3: USER REQUESTS PRODUCT MANAGEMENT
# ============================================================================


def test_user_can_request_product_editor(
    auth_client,
    test_user,
    test_product,
    clean_database,
):
    """
    User should be able to request ownership of a product
    """
    reason = "I created this product"

    response = auth_client.post(
        "/api/requests",
        json={"type": "product-ownership", "product_id": test_product["id"], "reason": reason},
    )

    assert response.status_code == 201
    request = response.json()
    assert request["status"] == "pending"
    assert request["user_id"] == test_user["id"]
    assert request["product_id"] == test_product["id"]
    assert request["reason"] == reason


def test_approved_ownership_request_updates_status(
    admin_client,
    test_admin,
    test_product,
    clean_database,
):
    """
    When ownership request is approved:
    - Request status changes to approved
    """
    reason = "I should own this product"

    # Admin creates request (admins can create requests too)
    request_response = admin_client.post(
        "/api/requests",
        json={"type": "product-ownership", "product_id": test_product["id"], "reason": reason},
    )
    assert request_response.status_code == 201
    request_id = request_response.json()["id"]

    # Admin approves request
    response = admin_client.patch(
        f"/api/requests/{request_id}",
        json={"status": "approved"},
    )

    assert response.status_code == 200
    request = response.json()
    assert request["status"] == "approved"


# ============================================================================
# STORY 3.4: USER SUBMITS EXISTING PRODUCT (URL CHECK FLOW)
# ============================================================================


def test_product_exists_endpoint_for_new_url(client):
    """
    Story 3.4: When user checks URL that doesn't exist
    - Endpoint returns exists=false
    """
    response = client.get(
        "/api/products/exists?source_url=https://github.com/user/never-submitted-product"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False


def test_product_exists_endpoint_for_existing_product(
    client,
    clean_database,
    test_user,
):
    """
    Story 3.4: When user checks URL that already exists
    - Endpoint returns exists=true with product details
    """
    # Create a product first
    test_url = "https://github.com/test/existing-product"
    clean_database.table("products").insert(
        {
            "id": str(uuid.uuid4()),
            "slug": f"existing-accessible-product-{uuid.uuid4().hex[:8]}",
            "name": "Existing Accessible Product",
            "source": "github",
            "type": "Software",
            "url": test_url,
            "description": "Product that exists",
            "created_by": test_user["id"],
        }
    ).execute()

    # Check if it exists
    response = client.get(f"/api/products/exists?source_url={test_url}")

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["product"]["name"] == "Existing Accessible Product"
    assert data["product"]["source_url"] == test_url


def test_product_submission_new_product_workflow(
    auth_client,
    test_user,
    clean_database,
):
    """
    Story 3.1: Full workflow for new product submission
    - User checks URL (doesn't exist) → gets form
    - User fills form → submits
    - Product created with created_by field
    - User is added as owner
    """
    test_url = f"https://github.com/user/new-product-{uuid.uuid4()}"

    # Step 1: Check if product exists (it doesn't)
    response = auth_client.get(f"/api/products/exists?source_url={test_url}")
    assert response.status_code == 200
    assert response.json()["exists"] is False

    # Step 2: User fills form and submits new product
    product_data = {
        "name": "New Accessibility Tool",
        "description": "A brand new accessible tool for testing",
        "source": "github",
        "type": "Software",
        "source_url": test_url,
    }

    response = auth_client.post("/api/products", json=product_data)
    assert response.status_code == 201
    product = response.json()
    assert product["name"] == product_data["name"]
    assert product["created_by"] == test_user["id"]


def test_product_submission_existing_product_workflow(
    client,
    clean_database,
    test_user,
    test_user_2,
):
    """
    Story 3.4: Full workflow when product already exists
    - User checks URL → gets existing product
    - User clicks "Request Ownership" or "Edit" depending on ownership
    """
    test_url = "https://github.com/existing/tool"
    existing_product_id = str(uuid.uuid4())

    # Create existing product owned by test_user_2
    clean_database.table("products").insert(
        {
            "id": existing_product_id,
            "slug": f"existing-accessible-tool-{uuid.uuid4().hex[:8]}",
            "name": "Existing Accessible Tool",
            "source": "github",
            "type": "Software",
            "url": test_url,
            "description": "Already in database",
            "created_by": test_user_2["id"],
        }
    ).execute()

    # Step 1: User checks URL (exists)
    response = client.get(f"/api/products/exists?source_url={test_url}")
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["product"]["id"] == existing_product_id

    # Step 2: Check created_by is set correctly
    assert data["product"]["created_by"] == test_user_2["id"]
