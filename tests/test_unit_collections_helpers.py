"""Unit tests for collections helper logic."""

import pytest

from routers import collections as collections_router

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTagsQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResponse(self.rows)


class _FakeDB:
    def __init__(self, tags_rows, product_tags_rows):
        self.tags_rows = tags_rows
        self.product_tags_rows = product_tags_rows

    def table(self, name: str):
        if name == "tags":
            return _FakeTagsQuery(self.tags_rows)
        if name == "product_tags":
            return _FakeTagsQuery(self.product_tags_rows)
        raise AssertionError(f"Unexpected table: {name}")


def test_safe_float_handles_valid_and_invalid_values():
    assert collections_router._safe_float("4.5") == 4.5
    assert collections_router._safe_float(3) == 3.0
    assert collections_router._safe_float("not-a-number") is None


def test_compute_display_rating_behaves_like_products_logic():
    assert collections_router._compute_display_rating(4.0, 2.0) == 3.0
    assert collections_router._compute_display_rating(4.0, None) == 4.0
    assert collections_router._compute_display_rating(None, 2.0) == 2.0
    assert collections_router._compute_display_rating(None, None) is None


def test_rating_meets_threshold_uses_display_rating_map():
    product = {"id": "p1"}
    ratings_map = {"p1": {"display_rating": 4.2}}
    assert collections_router._rating_meets_threshold(product, ratings_map, 4.0) is True
    assert collections_router._rating_meets_threshold(product, ratings_map, 4.5) is False


def test_get_product_ids_for_tags_or_mode():
    db = _FakeDB(
        tags_rows=[{"id": "t1", "name": "TagA"}, {"id": "t2", "name": "TagB"}],
        product_tags_rows=[
            {"product_id": "p1", "tag_id": "t1"},
            {"product_id": "p2", "tag_id": "t2"},
        ],
    )

    ids = collections_router._get_product_ids_for_tags(db, ["TagA", "TagB"], mode="or")
    assert ids == {"p1", "p2"}


def test_get_product_ids_for_tags_and_mode_requires_all_tags():
    db = _FakeDB(
        tags_rows=[{"id": "t1", "name": "TagA"}, {"id": "t2", "name": "TagB"}],
        product_tags_rows=[
            {"product_id": "p1", "tag_id": "t1"},
            {"product_id": "p1", "tag_id": "t2"},
            {"product_id": "p2", "tag_id": "t1"},
        ],
    )

    ids = collections_router._get_product_ids_for_tags(db, ["TagA", "TagB"], mode="and")
    assert ids == {"p1"}


def test_looks_like_uuid_helper():
    assert collections_router._looks_like_uuid("123e4567-e89b-12d3-a456-426614174000") is True
    assert collections_router._looks_like_uuid("not-a-uuid") is False
