"""Unit tests for the supported_sources name cache (no database needed)."""

import pytest

from services import supported_sources_cache as cache


class _FakeQuery:
    def __init__(self, db):
        self._db = db

    def select(self, *_args, **_kwargs):
        return self

    def execute(self):
        self._db.reads += 1
        if self._db.fail:
            raise RuntimeError("database unavailable")

        class _Resp:
            data = self._db.rows

        return _Resp()


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0
        self.fail = False

    def table(self, _name):
        return _FakeQuery(self)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.invalidate_supported_sources_cache()
    yield
    cache.invalidate_supported_sources_cache()


def test_second_read_is_served_from_cache():
    db = _FakeDb([{"name": " Github "}, {"name": "Ravelry"}, {"name": None}, {"name": "  "}])

    assert cache.get_supported_source_names(db) == ["Github", "Ravelry"]
    assert cache.get_supported_source_names(db) == ["Github", "Ravelry"]
    assert db.reads == 1


def test_invalidate_forces_a_fresh_read():
    db = _FakeDb([{"name": "Github"}])
    cache.get_supported_source_names(db)

    db.rows = [{"name": "Github"}, {"name": "Thingiverse"}]
    cache.invalidate_supported_sources_cache()

    assert cache.get_supported_source_names(db) == ["Github", "Thingiverse"]
    assert db.reads == 2


def test_entry_expires_after_ttl(monkeypatch):
    db = _FakeDb([{"name": "Github"}])
    now = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    cache.get_supported_source_names(db)

    now[0] += cache._TTL_SECONDS - 1
    cache.get_supported_source_names(db)
    assert db.reads == 1

    now[0] += 2
    cache.get_supported_source_names(db)
    assert db.reads == 2


def test_failed_read_is_not_cached():
    db = _FakeDb([{"name": "Github"}])
    db.fail = True
    with pytest.raises(RuntimeError):
        cache.get_supported_source_names(db)

    db.fail = False
    assert cache.get_supported_source_names(db) == ["Github"]
    assert db.reads == 2


def test_callers_cannot_mutate_the_cached_list():
    db = _FakeDb([{"name": "Github"}])
    cache.get_supported_source_names(db).append("Injected")

    assert cache.get_supported_source_names(db) == ["Github"]
