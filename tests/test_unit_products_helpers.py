"""Unit tests for product helper/filter logic."""

import pytest
from fastapi import HTTPException

from routers import products as products_router

pytestmark = pytest.mark.unit


class _FakeQuery:
    def __init__(self):
        self.calls = []

    def in_(self, field, values):
        self.calls.append(("in", field, list(values)))
        return self

    def ilike(self, field, value):
        self.calls.append(("ilike", field, value))
        return self

    def eq(self, field, value):
        self.calls.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.calls.append(("gte", field, value))
        return self

    def or_(self, value):
        self.calls.append(("or", value))
        return self


def test_normalize_list_handles_csv_and_lists():
    assert products_router._normalize_list(None) == []
    assert products_router._normalize_list("Github, Thingiverse") == ["Github", "Thingiverse"]
    assert products_router._normalize_list(["Github,Thingiverse", "Ravelry"]) == [
        "Github",
        "Thingiverse",
        "Ravelry",
    ]


def test_compute_display_rating_fallbacks_and_average():
    assert products_router._compute_display_rating(4.0, 2.0) == 3.0
    assert products_router._compute_display_rating(4.0, None) == 4.0
    assert products_router._compute_display_rating(None, 2.0) == 2.0
    assert products_router._compute_display_rating(None, None) is None


def test_without_min_rating_copies_and_clears_field():
    original = {"source_values": {"Github"}, "min_rating": 4.0}
    updated = products_router._without_min_rating(original)
    assert updated["min_rating"] is None
    assert original["min_rating"] == 4.0


def test_prepare_filters_rejects_sources_alias_when_disabled():
    with pytest.raises(HTTPException, match="'sources' is not supported") as exc:
        products_router._prepare_product_filters(
            db=None,
            current_user=None,
            source=None,
            sources=["Thingiverse"],
            allow_aliases=False,
        )
    assert exc.value.status_code == 400


def test_prepare_filters_rejects_types_alias_when_disabled():
    with pytest.raises(HTTPException, match="'types' is not supported") as exc:
        products_router._prepare_product_filters(
            db=None,
            current_user=None,
            type=None,
            types=["Hardware"],
            allow_aliases=False,
        )
    assert exc.value.status_code == 400


def test_prepare_filters_rejects_include_banned_for_regular_user():
    with pytest.raises(HTTPException, match="Moderator or admin role required") as exc:
        products_router._prepare_product_filters(
            db=None,
            current_user={"id": "u1", "role": "user"},
            include_banned=True,
        )
    assert exc.value.status_code == 403


def test_prepare_filters_allows_include_banned_for_admin():
    filters = products_router._prepare_product_filters(
        db=None,
        current_user={"id": "admin-1", "role": "admin"},
        include_banned=True,
    )
    assert filters["include_banned"] is True


def test_apply_product_filters_returns_none_when_tag_filter_has_no_matches(monkeypatch):
    query = _FakeQuery()
    monkeypatch.setattr(products_router, "get_product_ids_for_tags", lambda *_args, **_kwargs: set())

    filters = {
        "source_values": set(),
        "type_values": set(),
        "tag_values": ["missing"],
        "tag_mode": "or",
        "search": None,
        "created_by": None,
        "include_banned": False,
        "updated_since": None,
        "min_rating": None,
    }

    assert products_router._apply_product_filters(query, db=None, filters=filters) is None


def test_apply_product_filters_adds_expected_clauses():
    query = _FakeQuery()
    filters = {
        "source_values": {"Github"},
        "type_values": {"Software"},
        "tag_values": [],
        "tag_mode": "or",
        "search": "screen",
        "created_by": "user-1",
        "include_banned": False,
        "updated_since": "2026-01-01T00:00:00+00:00",
        "min_rating": 4.0,
    }

    result = products_router._apply_product_filters(query, db=None, filters=filters)
    assert result is query
    assert ("in", "source", ["Github"]) in query.calls
    assert ("in", "type", ["Software"]) in query.calls
    assert ("ilike", "name", "%screen%") in query.calls
    assert ("eq", "created_by", "user-1") in query.calls
    assert ("eq", "banned", False) in query.calls
    assert ("gte", "source_last_updated", "2026-01-01T00:00:00+00:00") in query.calls
    assert ("or", "computed_rating.gte.4.0,source_rating.gte.4.0") in query.calls
