import pytest
import uuid

from fastapi.testclient import TestClient

from main import app
from services.auth import get_current_user
from services.database import get_db

pytestmark = pytest.mark.integration

# Map human-readable placeholders to stable UUIDs for test users
_PLACEHOLDER_USER_IDS: dict[str, str] = {}


def _ensure_uuid(value: str) -> str:
    """Return a valid UUID string, allocating one for placeholders."""
    try:
        uuid.UUID(value)
        return value
    except Exception:
        if value not in _PLACEHOLDER_USER_IDS:
            _PLACEHOLDER_USER_IDS[value] = str(uuid.uuid4())
        return _PLACEHOLDER_USER_IDS[value]


@pytest.fixture
def client_with_db(clean_database):
    """Test client with DB override; auth is controlled per-test via auth_header."""
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: clean_database
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_header(request, clean_database, test_user):
    """Factory to set current user override and return headers."""

    def _make(user_id: str):
        actual_id = _ensure_uuid(user_id)
        # Ensure user exists; if not, create minimal record
        existing = clean_database.table("users").select("*").eq("id", actual_id).execute().data
        if not existing:
            clean_database.table("users").insert(
                {
                    "id": actual_id,
                    "github_id": f"gh-{user_id}",
                    "username": f"user-{user_id}",
                    "display_name": user_id,
                    "email": f"{str(user_id).replace(' ', '-')[:40]}@example.com",
                    "role": "user",
                }
            ).execute()

        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: clean_database
        app.dependency_overrides[get_current_user] = lambda: {"id": actual_id}
        return {}

    def teardown():
        app.dependency_overrides.clear()

    request.addfinalizer(teardown)
    return _make


@pytest.fixture
def test_product(clean_database, test_user):
    """Create a test product owned by test_user."""
    product_id = str(uuid.uuid4())
    product = (
        clean_database.table("products")
        .insert(
            {
                "id": product_id,
                "name": "Test Product",
                "type": "Software",
                "source": "github",
                "slug": f"test-product-{uuid.uuid4().hex[:8]}",
                "url": f"https://github.com/test/product-{uuid.uuid4().hex[:8]}",
                "description": "A test product",
                "created_by": test_user["id"],
            }
        )
        .execute()
    )
    yield product.data[0]
    clean_database.table("product_urls").delete().eq("product_id", product_id).execute()
    clean_database.table("products").delete().eq("id", product_id).execute()


@pytest.fixture
def test_product_url(clean_database, test_product, test_user):
    """Create a test product URL owned by test_user."""
    url = (
        clean_database.table("product_urls")
        .insert(
            {
                "product_id": test_product["id"],
                "url": "https://example.com/resource",
                "description": "Test resource",
                "created_by": test_user["id"],
            }
        )
        .execute()
    )
    yield url.data[0]
    clean_database.table("product_urls").delete().eq("id", url.data[0]["id"]).execute()


def test_add_product_url_as_owner(test_product, client_with_db, auth_header):
    response = client_with_db.post(
        f"/api/products/{test_product['id']}/urls",
        json={"url": "https://github.com/example/repo", "description": "Source repository"},
        headers=auth_header(test_product["created_by"]),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://github.com/example/repo"
    assert body["description"] == "Source repository"
    assert body["product_id"] == test_product["id"]
    assert body["created_by"] == test_product["created_by"]


def test_add_product_url_unauthorized(test_product, client_with_db, auth_header):
    response = client_with_db.post(
        f"/api/products/{test_product['id']}/urls",
        json={"url": "https://github.com/example/repo", "description": "Source repository"},
        headers=auth_header("different-user"),
    )
    assert response.status_code == 403


def test_add_product_url_product_not_found(client_with_db, auth_header):
    missing_id = str(uuid.uuid4())
    response = client_with_db.post(
        f"/api/products/{missing_id}/urls",
        json={"url": "https://example.com", "description": "Test"},
        headers=auth_header("test-user-1"),
    )
    assert response.status_code == 404


def test_get_product_urls(test_product, test_product_url, client_with_db):
    response = client_with_db.get(f"/api/products/{test_product['id']}/urls")
    assert response.status_code == 200
    urls = response.json()
    assert isinstance(urls, list)
    assert any(u["url"] == test_product_url["url"] for u in urls)
    first = urls[0]
    assert first["product_id"] == test_product["id"]


def test_get_product_urls_empty(client_with_db, auth_header):
    product_response = client_with_db.post(
        "/api/products",
        json={
            "name": "Empty Product",
            "type": "Software",
            "description": "No URLs",
        },
        headers=auth_header("new-owner"),
    )
    if product_response.status_code == 201:
        product_id = product_response.json()["id"]
        response = client_with_db.get(f"/api/products/{product_id}/urls")
        assert response.status_code == 200
        assert response.json() == []


def test_update_product_url_by_creator(test_product, test_product_url, client_with_db, auth_header):
    response = client_with_db.patch(
        f"/api/products/{test_product['id']}/urls/{test_product_url['id']}",
        json={"description": "Updated description"},
        headers=auth_header(test_product_url["created_by"]),
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"
    assert response.json()["url"] == test_product_url["url"]


def test_update_product_url_by_owner(
    test_product, test_product_url, clean_database, client_with_db, auth_header
):
    second_owner_id = _ensure_uuid("test-user-2")
    clean_database.table("users").insert(
        {
            "id": second_owner_id,
            "github_id": f"gh-{second_owner_id[:8]}",
            "username": f"user-{second_owner_id[:8]}",
            "display_name": "Second Owner",
            "email": f"owner-{second_owner_id[:8]}@example.com",
            "role": "user",
        }
    ).execute()
    clean_database.table("product_editors").insert(
        {
            "product_id": test_product["id"],
            "user_id": second_owner_id,
        }
    ).execute()

    response = client_with_db.patch(
        f"/api/products/{test_product['id']}/urls/{test_product_url['id']}",
        json={"description": "Updated by owner"},
        headers=auth_header(second_owner_id),
    )
    assert response.status_code == 200


def test_update_product_url_unauthorized(
    test_product, test_product_url, client_with_db, auth_header
):
    response = client_with_db.patch(
        f"/api/products/{test_product['id']}/urls/{test_product_url['id']}",
        json={"description": "Hacked!"},
        headers=auth_header("malicious-user"),
    )
    assert response.status_code == 403


def test_delete_product_url_as_owner(test_product, test_product_url, client_with_db, auth_header):
    response = client_with_db.delete(
        f"/api/products/{test_product['id']}/urls/{test_product_url['id']}",
        headers=auth_header(test_product["created_by"]),
    )
    assert response.status_code == 204


def test_delete_product_url_unauthorized(
    test_product, test_product_url, client_with_db, auth_header
):
    response = client_with_db.delete(
        f"/api/products/{test_product['id']}/urls/{test_product_url['id']}",
        headers=auth_header("different-user"),
    )
    assert response.status_code == 403


def test_multiple_urls_per_product(test_product, client_with_db, auth_header):
    url1_response = client_with_db.post(
        f"/api/products/{test_product['id']}/urls",
        json={"url": "https://github.com/example/repo", "description": "GitHub"},
        headers=auth_header(test_product["created_by"]),
    )
    assert url1_response.status_code == 201

    url2_response = client_with_db.post(
        f"/api/products/{test_product['id']}/urls",
        json={"url": "https://example.com/docs", "description": "Documentation"},
        headers=auth_header(test_product["created_by"]),
    )
    assert url2_response.status_code == 201

    get_response = client_with_db.get(f"/api/products/{test_product['id']}/urls")
    assert get_response.status_code == 200
    urls = get_response.json()
    assert len(urls) >= 2
    assert any(u["description"] == "GitHub" for u in urls)
    assert any(u["description"] == "Documentation" for u in urls)


def test_url_validation(test_product, client_with_db, auth_header):
    response = client_with_db.post(
        f"/api/products/{test_product['id']}/urls",
        json={"url": "not-a-valid-url", "description": "Bad URL"},
        headers=auth_header("test-user-1"),
    )
    assert response.status_code >= 400
