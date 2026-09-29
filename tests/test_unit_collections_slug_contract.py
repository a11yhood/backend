"""Unit tests for the collection response's product_ids/product_slugs contract.

Part of https://github.com/a11yhood/backend/issues/197 ("Improve slug
reliability"): product_slugs must be index-aligned with product_ids,
including when a product's slug can't be resolved (None in the aligned
position, not dropped or reordered).
"""

import pytest

from routers import collections as collections_router

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResponse(self.rows)


class _FakeDB:
    def __init__(self, entries_rows, product_rows, editor_rows=None):
        self.entries_rows = entries_rows
        self.product_rows = product_rows
        self.editor_rows = editor_rows or []

    def table(self, name: str):
        if name == "collection_entries":
            return _FakeQuery(self.entries_rows)
        if name == "products":
            return _FakeQuery(self.product_rows)
        if name == "collection_editors":
            return _FakeQuery(self.editor_rows)
        raise AssertionError(f"Unexpected table: {name}")


def _entry_row(collection_id, product_id, position):
    return {
        "collection_id": collection_id,
        "kind": "product",
        "position": position,
        "label": None,
        "product_id": product_id,
        "collection_ref_id": None,
        "blog_post_id": None,
        "query_json": None,
    }


def test_product_slugs_ordering_matches_product_ids():
    # Entries deliberately out of position order, to prove sorting-by-position
    # (not insertion/query order) drives the final product_ids/product_slugs order.
    db = _FakeDB(
        entries_rows=[
            _entry_row("c1", "p3", 2),
            _entry_row("c1", "p1", 0),
            _entry_row("c1", "p2", 1),
        ],
        product_rows=[
            {"id": "p1", "slug": "slug-a"},
            {"id": "p2", "slug": "slug-b"},
            {"id": "p3", "slug": "slug-c"},
        ],
    )
    collection = {"id": "c1", "user_id": "owner"}

    collections_router._populate_collection_relationships(db, collection)

    assert collection["product_ids"] == ["p1", "p2", "p3"]
    assert collection["product_slugs"] == ["slug-a", "slug-b", "slug-c"]


def test_product_slugs_null_when_unresolvable_not_dropped_or_reordered():
    # p2 has an entry but no matching row in the products lookup response
    # (e.g. a lookup gap) -- must appear as None at its own index, not be
    # skipped (which would misalign every slug after it) or reorder the list.
    db = _FakeDB(
        entries_rows=[
            _entry_row("c1", "p1", 0),
            _entry_row("c1", "p2", 1),
            _entry_row("c1", "p3", 2),
        ],
        product_rows=[
            {"id": "p1", "slug": "slug-a"},
            {"id": "p3", "slug": "slug-c"},
        ],
    )
    collection = {"id": "c1", "user_id": "owner"}

    collections_router._populate_collection_relationships(db, collection)

    assert collection["product_ids"] == ["p1", "p2", "p3"]
    assert collection["product_slugs"] == ["slug-a", None, "slug-c"]
