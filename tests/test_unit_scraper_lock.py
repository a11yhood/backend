"""Unit tests for ScraperService's scraper_locks overlap guard.

These use an in-memory fake for the scraper_locks table so the lock's actual
acquire/release semantics (not just mocked return values) are exercised.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from services.scrapers import ScraperService

pytestmark = pytest.mark.unit


class _ScraperLocksTable:
    """In-memory stand-in for the scraper_locks table only."""

    def __init__(self):
        self.rows: dict[str, dict] = {}  # source -> {"locked_at": iso str, "lock_token": str}

    def delete(self):
        return _DeleteBuilder(self)

    def upsert(self, row, *, on_conflict=None, ignore_duplicates=False):
        return _UpsertBuilder(self, row, ignore_duplicates=ignore_duplicates)


class _DeleteBuilder:
    def __init__(self, table):
        self._table = table
        self._filters = {}
        self._lt = None

    def eq(self, column, value):
        assert column in ("source", "lock_token")
        self._filters[column] = value
        return self

    def lt(self, column, value):
        assert column == "locked_at"
        self._lt = value
        return self

    def execute(self):
        table = self._table
        source = self._filters.get("source")
        row = table.rows.get(source)
        if row is None:
            return type("Response", (), {"data": []})()

        if self._lt is not None and not (row["locked_at"] < self._lt):
            return type("Response", (), {"data": []})()
        if "lock_token" in self._filters and row["lock_token"] != self._filters["lock_token"]:
            return type("Response", (), {"data": []})()

        del table.rows[source]
        return type("Response", (), {"data": [row]})()


class _UpsertBuilder:
    def __init__(self, table, row, *, ignore_duplicates):
        self._table = table
        self._row = row
        self._ignore_duplicates = ignore_duplicates

    def execute(self):
        table = self._table
        source = self._row["source"]
        if source in table.rows and self._ignore_duplicates:
            return type("Response", (), {"data": []})()

        new_row = {
            "source": source,
            "locked_at": datetime.now(UTC).isoformat(),
            "lock_token": str(uuid.uuid4()),
        }
        table.rows[source] = new_row
        return type("Response", (), {"data": [dict(new_row)]})()


class _SupabaseStub:
    def __init__(self):
        self.scraper_locks = _ScraperLocksTable()

    def table(self, name):
        if name == "scraper_locks":
            return self.scraper_locks
        raise AssertionError(f"Unexpected table access in lock test: {name}")


def test_acquire_lock_succeeds_when_unheld():
    service = ScraperService(_SupabaseStub())
    token = service._try_acquire_scrape_lock("thingiverse")
    assert token is not None
    assert token != ""


def test_acquire_lock_fails_when_already_held():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    assert service._try_acquire_scrape_lock("thingiverse") is not None
    # A second, overlapping run for the same source must not proceed.
    assert service._try_acquire_scrape_lock("thingiverse") is None


def test_release_then_acquire_succeeds():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    token = service._try_acquire_scrape_lock("thingiverse")
    service._release_scrape_lock("thingiverse", token)
    assert service._try_acquire_scrape_lock("thingiverse") is not None


def test_stale_lock_is_reclaimed():
    stub = _SupabaseStub()
    service = ScraperService(stub)

    stale_time = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    stub.scraper_locks.rows["thingiverse"] = {
        "source": "thingiverse",
        "locked_at": stale_time,
        "lock_token": str(uuid.uuid4()),
    }

    # Older than _SCRAPE_LOCK_STALE_AFTER, so it should be cleared and reacquired.
    assert service._try_acquire_scrape_lock("thingiverse") is not None


def test_stale_reclaim_fences_off_original_owner_release():
    """Regression test: run A holds the lock past the stale window, run B
    reclaims it, and A's later release must not evict B's still-active lock.
    """
    stub = _SupabaseStub()
    service = ScraperService(stub)

    token_a = service._try_acquire_scrape_lock("thingiverse")
    assert token_a is not None

    # Simulate A's lock aging past the stale threshold while A is still running.
    stub.scraper_locks.rows["thingiverse"]["locked_at"] = (
        datetime.now(UTC) - timedelta(minutes=45)
    ).isoformat()

    token_b = service._try_acquire_scrape_lock("thingiverse")
    assert token_b is not None
    assert token_b != token_a

    # A finishes and releases using its own (stale) token: must be a no-op.
    service._release_scrape_lock("thingiverse", token_a)

    # B's lock must still be held, blocking a third overlapping run.
    assert service._try_acquire_scrape_lock("thingiverse") is None

    # B finishes and releases with its real token: now it's actually free.
    service._release_scrape_lock("thingiverse", token_b)
    assert service._try_acquire_scrape_lock("thingiverse") is not None


def test_different_sources_do_not_contend():
    service = ScraperService(_SupabaseStub())
    assert service._try_acquire_scrape_lock("thingiverse") is not None
    assert service._try_acquire_scrape_lock("ravelry") is not None


async def test_scrape_thingiverse_skips_when_lock_held(monkeypatch):
    stub = _SupabaseStub()
    stub.scraper_locks.rows["thingiverse"] = {
        "source": "thingiverse",
        "locked_at": datetime.now(UTC).isoformat(),
        "lock_token": str(uuid.uuid4()),
    }
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


async def test_scrape_thingiverse_releases_lock_with_its_own_token(monkeypatch):
    """The lock acquired for this run must be released, not left dangling,
    once the scrape completes."""
    stub = _SupabaseStub()
    service = ScraperService(stub)

    async def _fake_scrape(*args, **kwargs):
        return {"status": "success", "source": "Thingiverse"}

    monkeypatch.setattr(service, "_scrape_thingiverse_core", _fake_scrape)

    result = await service.scrape_thingiverse(access_token="token")

    assert result["status"] == "success"
    assert "thingiverse" not in stub.scraper_locks.rows
