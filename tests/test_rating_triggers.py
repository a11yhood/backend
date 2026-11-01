"""computed_rating maintenance by the statement-level ratings triggers (issue #65).

These run against the Supabase test project and need
migrations/20261013_batch_computed_rating_triggers.sql to be applied there.
"""
from uuid import uuid4


def _make_product(db, user, **extra):
    row = {
        "name": f"Rating Trigger {uuid4().hex[:8]}",
        "description": "computed_rating trigger test",
        "source": "github",
        "source_url": f"https://github.com/test/rating-trigger-{uuid4()}",
        "slug": f"rating-trigger-{uuid4()}",
        "created_by": user["id"],
        **extra,
    }
    return db.table("products").insert(row).execute().data[0]


def _computed(db, product_id):
    rows = db.table("products").select("computed_rating").eq("id", product_id).execute().data
    value = rows[0]["computed_rating"]
    return None if value is None else float(value)


def test_insert_with_source_rating_sets_computed_rating(clean_database, test_user):
    """BEFORE INSERT must use NEW.source_rating, not re-read a row that doesn't exist yet."""
    product = _make_product(clean_database, test_user, source_rating=4.0)
    assert _computed(clean_database, product["id"]) == 4.0


def test_bulk_insert_refreshes_every_product_once(clean_database, test_user, test_user_2):
    first = _make_product(clean_database, test_user)
    second = _make_product(clean_database, test_user, source_rating=2.0)

    clean_database.table("ratings").insert(
        [
            {"product_id": first["id"], "user_id": test_user["id"], "rating": 5},
            {"product_id": first["id"], "user_id": test_user_2["id"], "rating": 3},
            {"product_id": second["id"], "user_id": test_user["id"], "rating": 4},
        ]
    ).execute()

    assert _computed(clean_database, first["id"]) == 4.0  # avg(5, 3), no source rating
    # internal rating weighted by count, source rating is one extra vote: (4 + 2) / 2
    assert _computed(clean_database, second["id"]) == 3.0


def test_update_recomputes(clean_database, test_user):
    product = _make_product(clean_database, test_user)
    clean_database.table("ratings").insert(
        {"product_id": product["id"], "user_id": test_user["id"], "rating": 2}
    ).execute()
    assert _computed(clean_database, product["id"]) == 2.0

    clean_database.table("ratings").update({"rating": 5}).eq("product_id", product["id"]).execute()
    assert _computed(clean_database, product["id"]) == 5.0


def test_moving_a_rating_refreshes_old_and_new_product(clean_database, test_user):
    old = _make_product(clean_database, test_user)
    new = _make_product(clean_database, test_user)
    clean_database.table("ratings").insert(
        {"product_id": old["id"], "user_id": test_user["id"], "rating": 4}
    ).execute()
    assert _computed(clean_database, old["id"]) == 4.0

    clean_database.table("ratings").update({"product_id": new["id"]}).eq(
        "product_id", old["id"]
    ).execute()

    assert _computed(clean_database, old["id"]) is None
    assert _computed(clean_database, new["id"]) == 4.0


def test_delete_falls_back_to_source_rating(clean_database, test_user):
    product = _make_product(clean_database, test_user, source_rating=3.5)
    clean_database.table("ratings").insert(
        {"product_id": product["id"], "user_id": test_user["id"], "rating": 5}
    ).execute()
    assert _computed(clean_database, product["id"]) == 4.25

    clean_database.table("ratings").delete().eq("product_id", product["id"]).execute()
    assert _computed(clean_database, product["id"]) == 3.5


def test_source_rating_change_recomputes_with_existing_ratings(clean_database, test_user):
    product = _make_product(clean_database, test_user)
    clean_database.table("ratings").insert(
        {"product_id": product["id"], "user_id": test_user["id"], "rating": 4}
    ).execute()

    clean_database.table("products").update({"source_rating": 2.0}).eq(
        "id", product["id"]
    ).execute()

    assert _computed(clean_database, product["id"]) == 3.0
