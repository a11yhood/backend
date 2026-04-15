"""Test rating endpoints against the Supabase test database"""

import pytest

pytestmark = pytest.mark.integration


def test_get_ratings(client, clean_database, test_user, test_product):
    clean_database.table("ratings").insert(
        {
            "product_id": test_product["id"],
            "user_id": test_user["id"],
            "rating": 5,
        }
    ).execute()

    response = client.get("/api/ratings")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_rating_requires_auth(client, test_product):
    rating_data = {
        "product_id": test_product["id"],
        "rating": 5,
    }

    response = client.post("/api/ratings", json=rating_data)
    assert response.status_code == 401


def test_create_rating_success(auth_client, test_user, test_product):
    rating_data = {
        "product_id": test_product["id"],
        "rating": 5,
    }

    response = auth_client.post("/api/ratings", json=rating_data)
    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["user_id"] == test_user["id"]


def test_create_duplicate_rating_fails(auth_client, clean_database, test_user, test_product):
    clean_database.table("ratings").insert(
        {
            "product_id": test_product["id"],
            "user_id": test_user["id"],
            "rating": 4,
        }
    ).execute()

    response = auth_client.post(
        "/api/ratings",
        json={
            "product_id": test_product["id"],
            "rating": 5,
        },
    )
    assert response.status_code == 400
    assert "already rated" in response.json()["detail"].lower()


def test_update_rating_owner_only(auth_client, clean_database, test_user, test_product):
    rating = (
        clean_database.table("ratings")
        .insert(
            {
                "product_id": test_product["id"],
                "user_id": test_user["id"],
                "rating": 4,
            }
        )
        .execute()
        .data[0]
    )

    response = auth_client.put(f"/api/ratings/{rating['id']}", json={"rating": 5})
    assert response.status_code == 200
    assert response.json()["rating"] == 5


def test_delete_rating_owner_or_admin(auth_client, clean_database, test_user, test_product):
    rating = (
        clean_database.table("ratings")
        .insert(
            {
                "product_id": test_product["id"],
                "user_id": test_user["id"],
                "rating": 3,
            }
        )
        .execute()
        .data[0]
    )

    response = auth_client.delete(f"/api/ratings/{rating['id']}")
    assert response.status_code == 204
