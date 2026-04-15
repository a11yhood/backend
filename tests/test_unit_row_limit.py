"""Unit tests for dev-mode row limit helper."""

import pytest

from database_adapter import _RowLimitedTableBuilder

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, count=None):
        self.count = count


class _FakeSupabaseSelect:
    def __init__(self, count_to_return=None, should_raise=False):
        self.count_to_return = count_to_return
        self.should_raise = should_raise

    def execute(self):
        if self.should_raise:
            raise RuntimeError("count failed")
        return _FakeResponse(count=self.count_to_return)


class _FakeSupabase:
    def __init__(self, count_to_return=None, should_raise=False):
        self.count_to_return = count_to_return
        self.should_raise = should_raise

    def table(self, _table_name):
        return self

    def select(self, *_args, **_kwargs):
        return _FakeSupabaseSelect(
            count_to_return=self.count_to_return,
            should_raise=self.should_raise,
        )


class _FakeBuilder:
    def __init__(self):
        self.insert_calls = []

    def insert(self, data, *args, **kwargs):
        self.insert_calls.append((data, args, kwargs))
        return "insert-forwarded"


def test_insert_forwards_when_under_limit():
    builder = _FakeBuilder()
    helper = _RowLimitedTableBuilder(
        builder=builder,
        supabase_client=_FakeSupabase(count_to_return=1),
        table_name="products",
        max_rows=20,
    )

    result = helper.insert({"name": "abc"})

    assert result == "insert-forwarded"
    assert len(builder.insert_calls) == 1


def test_insert_raises_when_at_limit():
    builder = _FakeBuilder()
    helper = _RowLimitedTableBuilder(
        builder=builder,
        supabase_client=_FakeSupabase(count_to_return=20),
        table_name="products",
        max_rows=20,
    )

    with pytest.raises(ValueError, match="Dev row limit exceeded"):
        helper.insert({"name": "abc"})

    assert len(builder.insert_calls) == 0


def test_insert_proceeds_if_count_check_fails():
    builder = _FakeBuilder()
    helper = _RowLimitedTableBuilder(
        builder=builder,
        supabase_client=_FakeSupabase(should_raise=True),
        table_name="products",
        max_rows=20,
    )

    result = helper.insert({"name": "abc"})

    assert result == "insert-forwarded"
    assert len(builder.insert_calls) == 1


def test_getattr_delegates_to_underlying_builder():
    builder = _FakeBuilder()
    builder.custom_attr = "value"
    helper = _RowLimitedTableBuilder(
        builder=builder,
        supabase_client=_FakeSupabase(count_to_return=0),
        table_name="products",
        max_rows=20,
    )

    assert helper.custom_attr == "value"
