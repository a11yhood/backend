"""Unit tests for slug/normalization helpers."""

import pytest

from services.id_generator import generate_id_with_uniqueness_check, normalize_to_snake_case

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, existing_ids: set[str]):
        self.existing_ids = existing_ids
        self._candidate = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, _column, value):
        self._candidate = value
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._candidate in self.existing_ids:
            return _FakeResponse([{"id": self._candidate}])
        return _FakeResponse([])


class _FakeDB:
    def __init__(self, existing_ids: set[str]):
        self._table = _FakeTable(existing_ids)

    def table(self, _table_name: str):
        return self._table


def test_normalize_to_snake_case_basic_examples():
    assert normalize_to_snake_case("My Product") == "my-product"
    assert normalize_to_snake_case("Star Rating Target") == "star-rating-target"
    assert normalize_to_snake_case("3D Printer") == "3d-printer"


def test_normalize_to_snake_case_strips_and_collapses_symbols():
    assert normalize_to_snake_case("  Hello---World!!  ") == "hello-world"
    assert normalize_to_snake_case("A___B   C") == "a-b-c"


def test_normalize_to_snake_case_empty_values():
    assert normalize_to_snake_case("") == ""
    assert normalize_to_snake_case(None) == ""


def test_generate_unique_id_returns_base_when_available():
    db = _FakeDB(existing_ids=set())

    result = generate_id_with_uniqueness_check("My Product", db, "products")

    assert result == "my-product"


def test_generate_unique_id_appends_2_on_first_collision():
    db = _FakeDB(existing_ids={"my-product"})

    result = generate_id_with_uniqueness_check("My Product", db, "products")

    assert result == "my-product-2"


def test_generate_unique_id_uses_next_available_suffix():
    db = _FakeDB(existing_ids={"my-product", "my-product-2", "my-product-3"})

    result = generate_id_with_uniqueness_check("My Product", db, "products")

    assert result == "my-product-4"
