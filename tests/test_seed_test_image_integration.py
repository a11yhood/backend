"""Integration test for seed_scripts.seed_test_image against the test database."""

import pytest

from seed_scripts.seed_test_image import (
    PRODUCT_SLUG,
    TEST_IMAGE_ALT,
    TEST_IMAGE_KEY,
    seed_image,
)
from seed_scripts.seed_test_product import seed_product

pytestmark = pytest.mark.integration


def test_seed_test_image_creates_image_and_links_product(clean_database):
    """Seed image script should create image row and link it to test-product."""
    seed_product()
    seed_image()

    image_rows = (
        clean_database.table("images")
        .select("id,canonical_key,canonical_url,default_alt")
        .eq("canonical_key", TEST_IMAGE_KEY)
        .limit(1)
        .execute()
        .data
    )
    assert image_rows
    image = image_rows[0]
    assert image["canonical_key"] == TEST_IMAGE_KEY
    assert image["default_alt"] == TEST_IMAGE_ALT

    product_rows = (
        clean_database.table("products")
        .select("id,slug,image_id,image_alt")
        .eq("slug", PRODUCT_SLUG)
        .limit(1)
        .execute()
        .data
    )
    assert product_rows
    product = product_rows[0]
    assert product["slug"] == PRODUCT_SLUG
    assert product["image_id"] == image["id"]
    assert product["image_alt"] == TEST_IMAGE_ALT
