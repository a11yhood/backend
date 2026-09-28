"""Unit tests for ScraperService's scraper_locks overlap guard.

These use an in-memory fake for the scraper_locks table so the lock's actual
acquire/release semantics (not just mocked return values) are exercised.
"""

from datetime import UTC, datetime, timedelta

import pytest

from services.scrapers import ScraperService

pytestmark = pytest.mark.unit


class _ScraperLocksTable:
    """In-memory stand-in for the scraper_locks table only."""

    def __init__(self):
        self.rows: dict[str, str] = {}  # source -> locked_at (isoformat)

    def delete(self):
        return _DeleteBuilder(self)

    def upsert(self, row, *, on_conflict=None, ignore_duplicates=False):
        return _UpsertBuilder(self, row, ignore_duplicates=ignore_duplicates)


class _DeleteBuilder:
    def __init__(self, table):
        self._table = table
        self._source = None
        self._lt = None

    def eq(self, column, value):
        assert column == "source"
        self._source = value
        return self

    def lt(self, column, value):
        assert column == "locked_at"
        self._lt = value
        return self

    def execute(self):
        table = self._table
        if self._source in table.rows and (self._lt is None or table.rows[self._source] < self._lt):
            del table.rows[self._source]
        return type("Response", (), {"data": []})()


class _UpsertBuilder:
    def __init__(self, table, row, *, ignore_duplicates):
        self._table = table
        self._row = row
        self._ignore_duplicates = ignore_duplicates

    def execute(self):
        table = self._table
        source = self._row["source"]
        if source in table.rows:
            if self._ignore_duplicates:
                return type("Response", (), {"data": []})()
            # merge-duplicates path is unused by ScraperService today.
            table.rows[source] = datetime.now(UTC).isoformat()
            return type("Response", (), {"data": [{"source": source}]})()

        table.rows[source] = datetime.now(UTC).isoformat()
        return type("Response", (), {"data": [{"source": source}]})()


class _SupabaseStub:
    def __init__(self):
        self.scraper_locks = _ScraperLocksTable()

    def table(self, name):
        if name == "scraper_locks":
            return self.scraper_locks
        raise AssertionError(f"Unexpected table access in lock test: {name}")


def test_acquire_lock_succeeds_when_unheld():
    service = ScraperService(_SupabaseStub())
    assert service._try_acquire_scrape_lock("thingiverse") is True


def test_acquire_lock_fails_when_already_held():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    assert service._try_acquire_scrape_lock("thingiverse") is True
    # A second, overlapping run for the same source must not proceed.
    assert service._try_acquire_scrape_lock("thingiverse") is False


def test_release_then_acquire_succeeds():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    assert service._try_acquire_scrape_lock("thingiverse") is True
    service._release_scrape_lock("thingiverse")
    assert service._try_acquire_scrape_lock("thingiverse") is True


def test_stale_lock_is_reclaimed():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    stale_time = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    stub.scraper_locks.rows["thingiverse"] = stale_time

    # Older than _SCRAPE_LOCK_STALE_AFTER, so it should be cleared and reacquired.
    assert service._try_acquire_scrape_lock("thingiverse") is True


def test_different_sources_do_not_contend():
    service = ScraperService(_SupabaseStub())
    assert service._try_acquire_scrape_lock("thingiverse") is True
    assert service._try_acquire_scrape_lock("ravelry") is True


async def test_scrape_thingiverse_skips_when_lock_held(monkeypatch):
    stub = _SupabaseStub()
    stub.scraper_locks.rows["thingiverse"] = datetime.now(UTC).isoformat()
    service = ScraperService(stub)

    called = False

    async def _should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        return {"status": "success"}

    monkeypatch.setattr(service, "_scrape_thingiverse_core", _should_not_run)
    monkeypatch.setattr(service, "_scrape_thingiverse_legacy", _should_not_run)

    result = await service.scrape_thingiverse(access_token="token")

    assert called is False
    assert result["status"] == "halted"
    assert result["source"] == "Thingiverse"
