"""Unit tests for collections helper logic."""

import pytest

from routers import collections as collections_router
from services.product_queries import get_product_ids_for_tags

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


class _CollectionEntriesQuery:
    def __init__(self, mode: str):
        self.mode = mode

    def select(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.mode == "missing":
            raise Exception('relation "collection_entries" does not exist')
        if self.mode == "transient":
            raise Exception("connection timeout")
        return _FakeResponse([{"id": "ok"}])


class _CollectionEntriesDB:
    def __init__(self, modes: list[str]):
        self.modes = modes
        self.calls = 0

    def table(self, name: str):
        if name != "collection_entries":
            raise AssertionError(f"Unexpected table: {name}")
        mode = self.modes[min(self.calls, len(self.modes) - 1)]
        self.calls += 1
        return _CollectionEntriesQuery(mode)


def test_safe_float_handles_valid_and_invalid_values():
    assert collections_router._safe_float("4.5") == 4.5
    assert collections_router._safe_float(3) == 3.0
    assert collections_router._safe_float("not-a-number") is None


def test_compute_display_rating_behaves_like_products_logic():
    assert collections_router._compute_display_rating(4.0, 2.0) == 3.0
    assert collections_router._compute_display_rating(4.0, 2.0, 3) == pytest.approx(3.5)
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

    ids = get_product_ids_for_tags(db, ["TagA", "TagB"], mode="or")
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

    ids = get_product_ids_for_tags(db, ["TagA", "TagB"], mode="and")
    assert ids == {"p1"}


def test_looks_like_uuid_helper():
    assert collections_router._looks_like_uuid("123e4567-e89b-12d3-a456-426614174000") is True
    assert collections_router._looks_like_uuid("not-a-uuid") is False


def test_is_rpc_not_found_error_matches_expected_messages():
    assert collections_router._is_rpc_not_found_error(
        Exception("Could not find the function replace_collection_entries")
    ) is True
    assert collections_router._is_rpc_not_found_error(
        Exception("PGRST202: function not found")
    ) is True
    assert collections_router._is_rpc_not_found_error(
        Exception("could not find function replace_collection_entries(p_collection_id)")
    ) is True
    assert collections_router._is_rpc_not_found_error(
        Exception("connection timeout")
    ) is False
    assert collections_router._is_rpc_not_found_error(
        Exception("permission denied for table collection_entries")
    ) is False


def test_collection_entries_table_available_does_not_cache_missing_table(monkeypatch):
    monkeypatch.setattr(collections_router, "_COLLECTION_ENTRIES_TABLE_AVAILABLE", None)
    db = _CollectionEntriesDB(["missing", "missing", "ok"])

    assert collections_router._collection_entries_table_available(db) is False
    assert collections_router._collection_entries_table_available(db) is False
    # Both calls probed the DB — missing result is never cached
    assert db.calls == 2


def test_collection_entries_table_available_caches_true_after_migration(monkeypatch):
    monkeypatch.setattr(collections_router, "_COLLECTION_ENTRIES_TABLE_AVAILABLE", None)
    db = _CollectionEntriesDB(["missing", "ok", "ok"])

    assert collections_router._collection_entries_table_available(db) is False
    assert collections_router._collection_entries_table_available(db) is True
    # Third call uses the cache — only two DB probes total
    assert collections_router._collection_entries_table_available(db) is True
    assert db.calls == 2


def test_collection_entries_table_available_does_not_cache_transient_failures(monkeypatch):
    monkeypatch.setattr(collections_router, "_COLLECTION_ENTRIES_TABLE_AVAILABLE", None)
    db = _CollectionEntriesDB(["transient", "ok"])

    with pytest.raises(Exception, match="timeout"):
        collections_router._collection_entries_table_available(db)

    assert collections_router._COLLECTION_ENTRIES_TABLE_AVAILABLE is None
    assert collections_router._collection_entries_table_available(db) is True
