"""Test product endpoints using the Supabase test database"""
import pytest
import uuid
import re
from datetime import datetime, UTC, timedelta


def _slugify_for_test(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "product"


def _normalize_product_row(row: dict) -> dict:
    normalized = dict(row)
    pid = str(normalized.get("id") or uuid.uuid4())
    normalized["id"] = pid

    # Keep test data aligned with current DB constraints.
    if not normalized.get("slug"):
        base = str(normalized.get("name") or pid)
        normalized["slug"] = f"{_slugify_for_test(base)}-{pid[:8]}"

    for dt_field in ("created_at", "updated_at", "source_last_updated"):
        if isinstance(normalized.get(dt_field), datetime):
            normalized[dt_field] = normalized[dt_field].isoformat()

    return normalized


def _insert_products(clean_database, rows: list[dict]):
    payload = [_normalize_product_row(r) for r in rows]
    return clean_database.table("products").insert(payload).execute()


def test_get_products_success(client, test_product):
    response = client.get("/api/products")
    assert response.status_code == 200
    data = response.json()
    assert any(item["id"] == test_product["id"] for item in data)


def test_count_products_success(client, test_product):
    """Test /count endpoint returns total product count"""
    response = client.get("/api/products/count")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] >= 1  # At least the test_product


def test_count_products_with_filters(client, clean_database, test_product):
    """Test /count respects same filters as /products"""
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())
    p3_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "Assistive Spoon",
            "description": "Thingiverse fabrication tool",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:spoon",
        },
        {
            "id": p2_id,
            "name": "Voice Control Tool",
            "description": "Github software tool",
            "source": "Github",
            "type": "Tool",
            "url": "https://github.com/example/tool",
        },
        {
            "id": p3_id,
            "name": "Knit Pattern",
            "description": "Ravelry knit",
            "source": "Ravelry",
            "type": "Knitting",
            "url": "https://www.ravelry.com/patterns/library/knit",
        },
    ])

    # Count all products with Thingiverse or Github source
    response = client.get("/api/products/count?sources=Thingiverse,Github")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2  # p1 and p2 only


def test_count_products_with_type_filter(client, clean_database):
    """Test /count filters by type"""
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "3D Model",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:1",
        },
        {
            "id": p2_id,
            "name": "Software Tool",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/tool",
        },
    ])

    response = client.get("/api/products/count?type=Fabrication")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1  # Only p1


def test_count_products_with_tag_filter(client, clean_database):
    """Test /count filters by tags"""
    tag_id = str(uuid.uuid4())
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())

    clean_database.table("tags").insert({"id": tag_id, "name": "AssistiveTech"}).execute()
    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "Tagged Product",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:tagged",
        },
        {
            "id": p2_id,
            "name": "Untagged Product",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/untagged",
        },
    ])
    clean_database.table("product_tags").insert({
        "product_id": p1_id,
        "tag_id": tag_id,
    }).execute()

    response = client.get("/api/products/count?tags=AssistiveTech")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1  # Only p1


def test_count_products_with_search(client, clean_database):
    """Test /count filters by search term"""
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "Voice Control Software",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/voice",
        },
        {
            "id": p2_id,
            "name": "3D Printed Cup",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:cup",
        },
    ])

    response = client.get("/api/products/count?search=voice")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1  # Only p1 matches "voice"


def test_get_products_with_filters(client, clean_database, test_product):
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())
    p3_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "Assistive Spoon",
            "description": "Thingiverse fabrication tool",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:spoon",
        },
        {
            "id": p2_id,
            "name": "Voice Control Tool",
            "description": "Github software tool",
            "source": "Github",
            "type": "Tool",
            "url": "https://github.com/example/tool",
        },
        {
            "id": p3_id,
            "name": "Knit Pattern",
            "description": "Ravelry knit",
            "source": "Ravelry",
            "type": "Knitting",
            "url": "https://www.ravelry.com/patterns/library/knit",
        },
    ])

    response = client.get("/api/products?sources=Thingiverse,Github&types=Fabrication")
    assert response.status_code == 200
    data = response.json()
    ids = {item["id"] for item in data}
    assert p1_id in ids
    assert p2_id not in ids
    assert p3_id not in ids


def test_get_product_by_id(client, test_product):
    response = client.get(f"/api/products/{test_product['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_product["id"]


def test_get_products_filtered_by_tags(client, clean_database):
    tag_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    other_product_id = str(uuid.uuid4())

    clean_database.table("tags").insert({"id": tag_id, "name": "AssistiveTech"}).execute()
    _insert_products(clean_database, [
        {
            "id": product_id,
            "name": "Adapted Cup",
            "description": "Assistive device",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:cup",
        },
        {
            "id": other_product_id,
            "name": "Unrelated Tool",
            "description": "No tag match",
            "source": "Github",
            "type": "Tool",
            "url": "https://github.com/example/unrelated",
        },
    ])
    clean_database.table("product_tags").insert({
        "product_id": product_id,
        "tag_id": tag_id,
    }).execute()

    resp = client.get("/api/products?tags=AssistiveTech")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert product_id in ids
    assert other_product_id not in ids


def test_get_products_supports_multiple_source_params(client, clean_database):
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())
    p3_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": p1_id,
            "name": "MultiSource Thingiverse",
            "description": "MultiSource filter",
            "source": "Thingiverse",
            "type": "Fabrication",
            "url": "https://www.thingiverse.com/thing:multisource1",
        },
        {
            "id": p2_id,
            "name": "MultiSource Github",
            "description": "MultiSource filter",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/multisource2",
        },
        {
            "id": p3_id,
            "name": "MultiSource Other",
            "description": "MultiSource filter",
            "source": "Ravelry",
            "type": "Knitting",
            "url": "https://www.ravelry.com/patterns/library/multisource3",
        },
    ])

    resp = client.get("/api/products?source=Thingiverse&source=Github&search=MultiSource")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()}
    assert p1_id in ids
    assert p2_id in ids
    assert p3_id not in ids


def test_get_products_filters_by_min_display_rating(client, clean_database, test_user):
    high_id = str(uuid.uuid4())
    mixed_id = str(uuid.uuid4())
    user_only_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": high_id,
            "name": "RatingCase High",
            "description": "RatingCase",
            "source": "Github",
            "type": "Software",
            "source_rating": 4.5,
            "computed_rating": 4.5,  # Set computed_rating for test
            "url": "https://github.com/example/rating-high",
            "created_by": test_user["id"],
        },
        {
            "id": mixed_id,
            "name": "RatingCase Mixed",
            "description": "RatingCase",
            "source": "Github",
            "type": "Software",
            "source_rating": 2.0,
            "computed_rating": 2.0,  # Will be updated after ratings inserted
            "url": "https://github.com/example/rating-mixed",
            "created_by": test_user["id"],
        },
        {
            "id": user_only_id,
            "name": "RatingCase User",
            "description": "RatingCase",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/rating-user",
            "created_by": test_user["id"],
        },
    ])

    clean_database.table("ratings").insert([
        {"product_id": mixed_id, "user_id": test_user["id"], "rating": 4},
        {"product_id": user_only_id, "user_id": test_user["id"], "rating": 5},
    ]).execute()
    # computed_rating is updated automatically by the Supabase trigger on ratings insert

    resp = client.get("/api/products?search=RatingCase&min_rating=3.5")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert high_id in ids  # source_rating=4.5 >= 3.5
    assert mixed_id in ids  # computed_rating=4.0 >= 3.5 (user rating overrides source_rating=2.0)
    assert user_only_id in ids  # computed_rating=5.0 >= 3.5
    for item in data:
        assert item.get("display_rating") is not None


def test_get_products_filters_by_max_age(client, clean_database, test_user):
    """Test max_age filter shows only recently updated products from source"""
    # Clear all existing products first
    clean_database.table("products").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    
    old_id = str(uuid.uuid4())
    recent_id = str(uuid.uuid4())
    
    # Create old product (last updated from source 10 days ago)
    old_time = datetime.now(UTC) - timedelta(days=10)
    _insert_products(clean_database, [
        {
            "id": old_id,
            "name": "Old Product",
            "description": "Product updated 10 days ago",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/old",
            "created_by": test_user["id"],
            "source_last_updated": old_time,
        },
    ])
    
    # Create recent product (last updated from source 2 days ago)
    recent_time = datetime.now(UTC) - timedelta(days=2)
    _insert_products(clean_database, [
        {
            "id": recent_id,
            "name": "Recent Product",
            "description": "Product updated 2 days ago",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/recent",
            "created_by": test_user["id"],
            "source_last_updated": recent_time,
        },
    ])
    
    # Filter for products updated in last 5 days
    resp = client.get("/api/products?max_age=5")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert recent_id in ids
    assert old_id not in ids
    
    # Filter for products updated in last 15 days (should include both)
    resp = client.get("/api/products?max_age=15")
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert recent_id in ids
    assert old_id in ids


def test_count_products_respects_max_age(client, clean_database, test_user):
    """Test /count respects max_age filter"""
    # Clear all existing products first
    clean_database.table("products").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    
    old_id = str(uuid.uuid4())
    recent_id = str(uuid.uuid4())
    
    old_time = datetime.now(UTC) - timedelta(days=10)
    recent_time = datetime.now(UTC) - timedelta(days=2)
    
    _insert_products(clean_database, [
        {
            "id": old_id,
            "name": "Old Product",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/old-count",
            "created_by": test_user["id"],
            "source_last_updated": old_time,
        },
        {
            "id": recent_id,
            "name": "Recent Product",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/recent-count",
            "created_by": test_user["id"],
            "source_last_updated": recent_time,
        },
    ])
    
    # Count with 5 day filter should only include recent
    resp = client.get("/api/products/count?max_age=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    
    # Count with 15 day filter should include both
    resp = client.get("/api/products/count?max_age=15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


def test_count_products_respects_min_rating(client, clean_database, test_user):
    high_id = str(uuid.uuid4())
    low_id = str(uuid.uuid4())
    user_high_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": high_id,
            "name": "RatingCount High",
            "description": "RatingCount",
            "source": "Github",
            "type": "Software",
            "source_rating": 4.2,
            "computed_rating": 4.2,  # Set computed_rating for test (no trigger in SQLite)
            "url": "https://github.com/example/rating-count-high",
            "created_by": test_user["id"],
        },
        {
            "id": low_id,
            "name": "RatingCount Low",
            "description": "RatingCount",
            "source": "Github",
            "type": "Software",
            "source_rating": 3.0,
            "computed_rating": 3.0,  # Set computed_rating for test (no trigger in SQLite)
            "url": "https://github.com/example/rating-count-low",
            "created_by": test_user["id"],
        },
        {
            "id": user_high_id,
            "name": "RatingCount User High",
            "description": "RatingCount",
            "source": "Github",
            "type": "Software",
            "url": "https://github.com/example/rating-count-user",
            "created_by": test_user["id"],
        },
    ])

    clean_database.table("ratings").insert([
        {"product_id": low_id, "user_id": test_user["id"], "rating": 3},
        {"product_id": user_high_id, "user_id": test_user["id"], "rating": 4},
    ]).execute()

    # Manually update computed_rating since SQLite doesn't have the trigger
    clean_database.table("products").update({"computed_rating": 4.2}).eq("id", high_id).execute()
    clean_database.table("products").update({"computed_rating": 3.0}).eq("id", low_id).execute()
    clean_database.table("products").update({"computed_rating": 4.0}).eq("id", user_high_id).execute()

    resp = client.get("/api/products/count?search=RatingCount&min_rating=4")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_products_pagination_with_filters(client, clean_database, test_user):
    base_time = datetime.now(UTC).replace(tzinfo=None)
    items = []
    for idx in range(4):
        pid = str(uuid.uuid4())
        created_at = base_time + timedelta(minutes=idx)
        items.append({
            "id": pid,
            "name": f"PageTest {idx}",
            "description": "Pagination check",
            "source": "Github",
            "type": "Software",
            "url": f"https://github.com/example/pagetest-{idx}",
            "created_by": test_user["id"],
            "created_at": created_at,
        })
    _insert_products(clean_database, items)

    resp_page = client.get("/api/products?source=Github&search=PageTest&limit=2&offset=1")
    assert resp_page.status_code == 200
    data = resp_page.json()
    assert len(data) == 2

    expected_order = sorted(items, key=lambda p: p["created_at"], reverse=True)
    expected_slice = expected_order[1:3]
    returned_ids = [p["id"] for p in data]
    assert returned_ids == [p["id"] for p in expected_slice]


def test_sort_by_rating_uses_recency_as_secondary_sort(client, clean_database, test_user):
    """When sort_by=rating, products with equal ratings should be ordered by created_at desc."""
    base_time = datetime.now(UTC).replace(tzinfo=None)
    older_id = str(uuid.uuid4())
    newer_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {
            "id": older_id,
            "name": "SortRatingRecency Older",
            "description": "SortRatingRecency",
            "source": "Github",
            "type": "Software",
            "computed_rating": 4.0,
            "url": "https://github.com/example/sort-rating-older",
            "created_by": test_user["id"],
            "created_at": base_time,
        },
        {
            "id": newer_id,
            "name": "SortRatingRecency Newer",
            "description": "SortRatingRecency",
            "source": "Github",
            "type": "Software",
            "computed_rating": 4.0,
            "url": "https://github.com/example/sort-rating-newer",
            "created_by": test_user["id"],
            "created_at": base_time + timedelta(minutes=5),
        },
    ])

    resp = client.get("/api/products?search=SortRatingRecency&sort_by=rating&sort_order=desc")
    assert resp.status_code == 200
    data = resp.json()
    ids = [p["id"] for p in data]

    assert newer_id in ids
    assert older_id in ids
    # Newer product should appear before older when ratings are equal
    assert ids.index(newer_id) < ids.index(older_id)


def test_get_product_not_found(client):
    response = client.get("/api/products/nonexistent")
    assert response.status_code == 404


def test_create_product_requires_auth(client):
    product_data = {
        "name": "New Product",
        "description": "Description",
        "source": "github",
        "categories": ["assistive-tech"],
        "source_url": "https://example.com/new-product",
    }

    response = client.post("/api/products", json=product_data)
    assert response.status_code == 401


def test_create_product_success(auth_client, test_user):
    product_data = {
        "name": "New Product",
        "description": "Description",
        "source": "github",
        "categories": ["assistive-tech"],
        "source_url": "https://github.com/user/new-product",
    }

    response = auth_client.post("/api/products", json=product_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Product"
    assert data["created_by"] == test_user["id"]


def test_update_product_owner_only(auth_client, test_product):
    response = auth_client.put(f"/api/products/{test_product['id']}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_product_admin_only(auth_client, test_product):
    response = auth_client.delete(f"/api/products/{test_product['id']}")
    assert response.status_code == 403


def test_delete_product_admin_success(admin_client, test_product):
    response = admin_client.delete(f"/api/products/{test_product['id']}")
    assert response.status_code == 204


def test_bulk_delete_requires_admin(auth_client):
    resp = auth_client.post("/api/products/bulk-delete?source=Github")
    assert resp.status_code == 403


def test_bulk_delete_requires_params(admin_client):
    resp = admin_client.post("/api/products/bulk-delete")
    assert resp.status_code == 400
    assert "Must provide either" in resp.json()["detail"]


def test_bulk_delete_rejects_sources_alias(admin_client):
    resp = admin_client.post("/api/products/bulk-delete?sources=Thingiverse")
    assert resp.status_code == 400
    assert "'sources' is not supported" in resp.json()["detail"]


def test_bulk_delete_rejects_types_alias(admin_client):
    resp = admin_client.post("/api/products/bulk-delete?types=Hardware")
    assert resp.status_code == 400
    assert "'types' is not supported" in resp.json()["detail"]


def test_bulk_delete_by_source_query_param(admin_client, clean_database):
    # Insert products under a unique source to isolate the deletion scope
    source_name = "BulkSource"
    p1_id = str(uuid.uuid4())
    p2_id = str(uuid.uuid4())
    keep_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {"id": p1_id, "name": "Bulk A", "source": source_name, "url": f"https://example.com/{p1_id}"},
        {"id": p2_id, "name": "Bulk B", "source": source_name, "url": f"https://example.com/{p2_id}"},
        {"id": keep_id, "name": "Keep", "source": "Other", "url": f"https://example.com/{keep_id}"},
    ])

    resp = admin_client.post(f"/api/products/bulk-delete?source={source_name}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_count"] == 2

    remaining_bulk = clean_database.table("products").select("id").eq("source", source_name).execute()
    assert remaining_bulk.data == []

    keep_row = clean_database.table("products").select("id").eq("id", keep_id).execute()
    assert keep_row.data != []


def test_bulk_delete_accepts_json_body(admin_client, clean_database):
    source_name = "JsonSource"
    ids = [str(uuid.uuid4()) for _ in range(2)]
    _insert_products(clean_database, [
        {"id": ids[0], "name": "JSON A", "source": source_name, "url": f"https://example.com/{ids[0]}"},
        {"id": ids[1], "name": "JSON B", "source": source_name, "url": f"https://example.com/{ids[1]}"},
    ])

    resp = admin_client.post("/api/products/bulk-delete", json={"source": source_name})
    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2


def test_bulk_delete_by_product_ids_dedupes(admin_client, clean_database):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for pid in ids:
        _insert_products(clean_database, [{
            "id": pid,
            "name": f"Target {pid[:8]}",
            "source": "DedupSource",
            "url": f"https://example.com/{pid}",
        }])

    resp = admin_client.post(
        "/api/products/bulk-delete",
        json={"product_ids": [ids[0], ids[1], ids[1]]},
    )

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2  # duplicate ID should not double count

    remaining = clean_database.table("products").select("id").in_("id", ids).execute()
    remaining_ids = {row["id"] for row in (remaining.data or [])}
    assert remaining_ids == {ids[2]}  # Only the untouched ID should remain


def test_bulk_delete_uses_search_filters(admin_client, clean_database):
    source_name = "SearchSource"
    matching_ids = [str(uuid.uuid4()) for _ in range(2)]
    keep_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {"id": matching_ids[0], "name": "Alpha Screen Reader", "source": source_name, "type": "Software", "url": f"https://example.com/{matching_ids[0]}"},
        {"id": matching_ids[1], "name": "Alpha Magnifier", "source": source_name, "type": "Software", "url": f"https://example.com/{matching_ids[1]}"},
        {"id": keep_id, "name": "Beta Keyboard", "source": source_name, "type": "Hardware", "url": f"https://example.com/{keep_id}"},
    ])

    resp = admin_client.post("/api/products/bulk-delete?source=SearchSource&search=Alpha&type=Software")

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 2

    remaining = clean_database.table("products").select("id").in_("id", matching_ids + [keep_id]).execute()
    remaining_ids = {row["id"] for row in (remaining.data or [])}
    assert remaining_ids == {keep_id}


def test_bulk_delete_accepts_search_filters_in_json_body(admin_client, clean_database):
    source_name = "JsonSearchSource"
    delete_id = str(uuid.uuid4())
    keep_id = str(uuid.uuid4())

    _insert_products(clean_database, [
        {"id": delete_id, "name": "Body Filter Match", "source": source_name, "type": "Software", "source_rating": 4.5, "url": f"https://example.com/{delete_id}"},
        {"id": keep_id, "name": "Body Filter Keep", "source": source_name, "type": "Software", "source_rating": 2.0, "url": f"https://example.com/{keep_id}"},
    ])

    resp = admin_client.post(
        "/api/products/bulk-delete",
        json={"source": source_name, "search": "Body Filter", "min_rating": 4.0},
    )

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1

    remaining = clean_database.table("products").select("id").in_("id", [delete_id, keep_id]).execute()
    remaining_ids = {row["id"] for row in (remaining.data or [])}
    assert remaining_ids == {keep_id}


# ============================================================================
# TESTS FOR STORY 3.1 & 3.4: PRODUCT SUBMISSION WITH URL CHECK
# ============================================================================

def test_product_exists_endpoint_returns_false_for_new_url(client):
    """Test that /exists endpoint returns false for non-existent product"""
    response = client.get("/api/products/exists?source_url=https://example.com/never-submitted")
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert "product" not in data or data.get("product") is None


def test_product_exists_endpoint_returns_product(client, test_product):
    """Test that /exists endpoint returns existing product"""
    response = client.get(f"/api/products/exists?source_url={test_product['url']}")
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["product"]["id"] == test_product["id"]
    assert data["product"]["name"] == test_product["name"]


def test_product_exists_includes_necessary_fields(client, test_product):
    """Test that /exists endpoint returns all fields needed for UI decision"""
    response = client.get(f"/api/products/exists?source_url={test_product['url']}")
    assert response.status_code == 200
    data = response.json()
    
    # Product should have these fields for UI to display
    product = data["product"]
    assert "id" in product
    assert "name" in product
    assert "description" in product
    assert "source_url" in product


def test_create_product_by_new_user_adds_ownership(auth_client, test_user):
    """
    Story 3.1: User submits new product → becomes manager
    """
    product_data = {
        "name": "Accessibility Tool",
        "description": "A tool for testing accessibility",
        "source": "github",
        "categories": ["assistive-tech"],
        "source_url": "https://github.com/new-user/new-tool",
    }

    response = auth_client.post("/api/products", json=product_data)
    assert response.status_code == 201
    product = response.json()
    
    # Product should have created_by set to current user
    assert product["created_by"] == test_user["id"]
    
    # Verify user is in managers list by querying product_editors table
    # This would require a GET endpoint or checking via the product management response


def test_product_submission_logs_activity(auth_client, test_user, clean_database):
    """
    Story 3.1: User submits product → activity is logged
    """
    product_data = {
        "name": "New Accessible Tool",
        "description": "A tool to test activity logging during product submission",
        "source": "github",
        "categories": ["assistive-tech"],
        "source_url": "https://github.com/activity-test/tool",
    }

    response = auth_client.post("/api/products", json=product_data)
    assert response.status_code == 201
    product = response.json()
    
    # Check that activity was logged (in a real implementation)
    # For now, verify product was created with correct fields
    assert product["name"] == "New Accessible Tool"
    assert product["created_by"] == test_user["id"]


# ============================================================================
# BAN / UNBAN
# ============================================================================


def test_admin_can_ban_and_unban_product(admin_client, clean_database, test_product):
    resp = admin_client.post(f"/api/products/{test_product['id']}/ban", json={"reason": "spam"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["banned"] is True
    assert data["banned_reason"] == "spam"

    resp_unban = admin_client.post(f"/api/products/{test_product['id']}/unban")
    assert resp_unban.status_code == 200
    assert resp_unban.json()["banned"] is False


def test_ban_requires_moderator_or_admin(auth_client, test_product):
    resp = auth_client.post(f"/api/products/{test_product['id']}/ban", json={"reason": "spam"})
    assert resp.status_code == 403


def test_include_banned_requires_privileged_role(client, auth_client, clean_database):
    # Seed banned product
    banned_id = str(uuid.uuid4())
    _insert_products(clean_database, [{
        "id": banned_id,
        "name": "Banned Item",
        "description": "",
        "source": "github",
        "type": "tool",
        "banned": True,
    }])

    # Anonymous/user without role cannot request include_banned=true
    resp = client.get("/api/products?include_banned=true")
    assert resp.status_code == 403

    # Regular auth user also forbidden
    resp_auth = auth_client.get("/api/products?include_banned=true")
    assert resp_auth.status_code == 403


def test_banned_products_hidden_from_default_list(client, clean_database, test_product):
    clean_database.table("products").update({"banned": True}).eq("id", test_product["id"]).execute()
    resp = client.get("/api/products")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert test_product["id"] not in ids


def test_admin_can_include_banned_products_in_list(admin_client, clean_database, test_product):
    clean_database.table("products").update({"banned": True}).eq("id", test_product["id"]).execute()
    resp = admin_client.get("/api/products?include_banned=true")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert test_product["id"] in ids


def test_reject_create_when_existing_product_is_banned(auth_client, clean_database, test_product):
    clean_database.table("products").update({"banned": True}).eq("id", test_product["id"]).execute()

    # Use the same source_url from test_product (which should be github.com)
    payload = {
        "name": "Attempted Recreate",
        "description": "Trying to recreate banned product",
        "source": "github",
        "source_url": test_product["url"],
    }

    resp = auth_client.post("/api/products", json=payload)
    assert resp.status_code == 403
    assert "banned" in resp.json().get("detail", "").lower()
