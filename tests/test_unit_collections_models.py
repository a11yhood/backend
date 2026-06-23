"""Unit tests for typed collection entry models."""

import pytest
from pydantic import ValidationError

from models.collections import CollectionCreate

pytestmark = pytest.mark.unit


def test_collection_create_accepts_typed_entries():
    payload = CollectionCreate(
        name="Nested Collection",
        description="test",
        entries=[
            {"kind": "product", "product_id": "p1", "position": 0},
            {"kind": "collection", "collection_id": "c1", "position": 1},
            {"kind": "blogPost", "blog_post_id": "b1", "position": 2},
            {
                "kind": "query",
                "position": 3,
                "query": {
                    "search": "wheelchair",
                    "tags": ["Mobility"],
                    "tags_mode": "or",
                },
            },
        ],
    )

    assert payload.entries is not None
    assert payload.entries[0].kind == "product"
    assert payload.entries[1].kind == "collection"
    assert payload.entries[2].kind == "blogPost"
    assert payload.entries[3].kind == "query"


def test_collection_create_rejects_invalid_entry_kind_payload():
    with pytest.raises(ValidationError):
        CollectionCreate(
            name="Broken",
            entries=[
                {"kind": "product", "collection_id": "c1"},
            ],
        )
