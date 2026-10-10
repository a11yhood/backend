"""Reset must not disconnect platforms that were authorized in the test project."""

import pytest

from services import dev_mode


class _Table:
    def __init__(self, store):
        self.store = store
        self._upsert = None

    def select(self, *_args):
        return self

    def upsert(self, row, on_conflict=None):
        self._upsert = row
        return self

    def execute(self):
        if self._upsert is not None:
            self.store["restored"].append(self._upsert)
            return type("R", (), {"data": [self._upsert]})()
        return type("R", (), {"data": self.store["oauth_rows"]})()


class _Db:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        assert name == "oauth_configs"
        return _Table(self.store)


def test_snapshot_keeps_only_rows_with_a_token():
    store = {
        "oauth_rows": [
            {"platform": "ravelry", "access_token": "tok", "refresh_token": "r"},
            {"platform": "github", "access_token": None},
            {"platform": "thingiverse", "access_token": ""},
        ],
        "restored": [],
    }

    kept = dev_mode._snapshot_connected_oauth_configs(_Db(store))

    assert [r["platform"] for r in kept] == ["ravelry"]


@pytest.mark.asyncio
async def test_reset_and_reseed_restores_connected_oauth_rows(monkeypatch):
    store = {
        "oauth_rows": [{"platform": "ravelry", "access_token": "tok", "refresh_token": "r"}],
        "restored": [],
    }
    db = _Db(store)
    monkeypatch.setattr(dev_mode, "get_db", lambda: db)

    async def fake_reset():
        store["oauth_rows"] = [{"platform": "ravelry", "access_token": None}]  # wiped + reseeded
        return {"cleared_tables": {}}

    monkeypatch.setattr(dev_mode, "reset_database", fake_reset)
    monkeypatch.setattr(dev_mode, "get_seed_manifest", lambda: {"seed_version": "x"})

    import seed_scripts.seed_all as seed_all

    monkeypatch.setattr(seed_all, "main", lambda: 0)

    result = await dev_mode.reset_and_reseed_database()

    assert result["seeded"] is True
    assert store["restored"] == [{"platform": "ravelry", "access_token": "tok", "refresh_token": "r"}]
