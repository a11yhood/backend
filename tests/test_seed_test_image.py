"""Unit tests for seed_scripts.seed_test_image."""

from unittest.mock import MagicMock

import pytest

from seed_scripts import seed_test_image

pytestmark = pytest.mark.unit


def _response(data):
    resp = MagicMock()
    resp.data = data
    return resp


def test_seed_image_upserts_image_and_links_product(monkeypatch):
    mock_db = MagicMock()
    mock_settings = MagicMock()

    images_table = MagicMock()
    products_table = MagicMock()
    users_table = MagicMock()

    users_table.upsert.return_value.execute.return_value = _response([
        {"id": seed_test_image.ADMIN_USER_ID}
    ])
    users_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = _response([
        {"id": seed_test_image.ADMIN_USER_ID}
    ])

    # Image upsert returns seeded image id
    images_table.upsert.return_value.execute.return_value = _response(
        [{"id": seed_test_image.TEST_IMAGE_ID}]
    )

    # Product lookup returns seeded test product
    products_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = _response(
        [{"id": "prod-123", "slug": seed_test_image.PRODUCT_SLUG}]
    )

    # Product update succeeds
    products_table.update.return_value.eq.return_value.execute.return_value = _response(
        [{"id": "prod-123"}]
    )

    def table_side_effect(name):
        if name == "users":
            return users_table
        if name == "images":
            return images_table
        if name == "products":
            return products_table
        raise AssertionError(f"Unexpected table name: {name}")

    mock_db.table.side_effect = table_side_effect

    monkeypatch.setattr(seed_test_image, "get_settings", lambda _: mock_settings)
    monkeypatch.setattr(seed_test_image, "DatabaseAdapter", lambda _: mock_db)

    seed_test_image.seed_image()

    images_table.upsert.assert_called_once()
    users_table.upsert.assert_called_once()
    upsert_args = images_table.upsert.call_args.args[0]
    assert upsert_args["canonical_key"] == seed_test_image.TEST_IMAGE_KEY
    assert upsert_args["canonical_url"] == seed_test_image.TEST_IMAGE_URL

    products_table.update.assert_called_once_with(
        {
            "image_id": seed_test_image.TEST_IMAGE_ID,
            "image_alt": seed_test_image.TEST_IMAGE_ALT,
        }
    )


def test_seed_image_handles_missing_product(monkeypatch):
    mock_db = MagicMock()
    mock_settings = MagicMock()

    images_table = MagicMock()
    products_table = MagicMock()
    users_table = MagicMock()

    users_table.upsert.return_value.execute.return_value = _response([
        {"id": seed_test_image.ADMIN_USER_ID}
    ])
    users_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = _response([
        {"id": seed_test_image.ADMIN_USER_ID}
    ])

    images_table.upsert.return_value.execute.return_value = _response(
        [{"id": seed_test_image.TEST_IMAGE_ID}]
    )
    products_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = _response([])

    def table_side_effect(name):
        if name == "users":
            return users_table
        if name == "images":
            return images_table
        if name == "products":
            return products_table
        raise AssertionError(f"Unexpected table name: {name}")

    mock_db.table.side_effect = table_side_effect

    monkeypatch.setattr(seed_test_image, "get_settings", lambda _: mock_settings)
    monkeypatch.setattr(seed_test_image, "DatabaseAdapter", lambda _: mock_db)

    seed_test_image.seed_image()

    # Missing product should skip product update rather than crash.
    products_table.update.assert_not_called()
