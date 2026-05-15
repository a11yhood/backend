"""Unit tests for dev auth token parsing logic."""

import pytest
from fastapi import HTTPException

from services import auth

pytestmark = pytest.mark.unit


class _FakeSettings:
    def __init__(self, test_mode: bool):
        self.TEST_MODE = test_mode


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeUsersTable:
    def __init__(self, users_by_id=None, users_by_username=None):
        self.users_by_id = users_by_id or {}
        self.users_by_username = users_by_username or {}
        self._current_column = None
        self._current_value = None
        self.inserted_rows = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._current_column = column
        self._current_value = value
        return self

    def insert(self, row):
        self.inserted_rows.append(row)
        return self

    def execute(self):
        if self._current_column == "id":
            row = self.users_by_id.get(self._current_value)
            return _FakeResponse([row] if row else [])
        if self._current_column == "username":
            row = self.users_by_username.get(self._current_value)
            return _FakeResponse([row] if row else [])
        return _FakeResponse([])


class _FakeDB:
    def __init__(self, users_table: _FakeUsersTable):
        self.users_table = users_table

    def table(self, name: str):
        assert name == "users"
        return self.users_table


def _enable_test_mode(monkeypatch):
    monkeypatch.setattr(auth, "load_settings_from_env", lambda: _FakeSettings(True))


def test_rejects_dev_tokens_when_not_in_test_mode(monkeypatch):
    monkeypatch.setattr(auth, "load_settings_from_env", lambda: _FakeSettings(False))
    db = _FakeDB(_FakeUsersTable())

    with pytest.raises(HTTPException, match="Dev tokens only in TEST_MODE") as exc:
        import asyncio

        asyncio.run(auth.parse_dev_token(authorization="Bearer dev-token-user", x_dev_role=None, db=db))

    assert exc.value.status_code == 401


def test_rejects_when_headers_missing(monkeypatch):
    _enable_test_mode(monkeypatch)
    db = _FakeDB(_FakeUsersTable())
    monkeypatch.setattr(auth, "get_db", lambda: db)

    with pytest.raises(HTTPException, match="No authorization header") as exc:
        import asyncio

        asyncio.run(auth.parse_dev_token(authorization=None, x_dev_role=None, db=db))

    assert exc.value.status_code == 401


def test_rejects_invalid_token_format(monkeypatch):
    _enable_test_mode(monkeypatch)
    db = _FakeDB(_FakeUsersTable())
    monkeypatch.setattr(auth, "get_db", lambda: db)

    with pytest.raises(HTTPException, match="Invalid dev token format") as exc:
        import asyncio

        asyncio.run(auth.parse_dev_token(authorization="Bearer not-a-dev-token", x_dev_role=None, db=db))

    assert exc.value.status_code == 401


def test_uuid_token_resolves_exact_seeded_user(monkeypatch):
    _enable_test_mode(monkeypatch)
    user_id = "2a3b7c3e-971b-4b42-9c8c-0f1843486c50"
    seeded_user = {
        "id": user_id,
        "username": "regular_user",
        "email": "user@example.com",
        "role": "user",
    }
    db = _FakeDB(_FakeUsersTable(users_by_id={user_id: seeded_user}))
    monkeypatch.setattr(
        auth,
        "get_db",
        lambda: db,
    )

    import asyncio

    result = asyncio.run(
        auth.parse_dev_token(authorization=f"Bearer dev-token-{user_id}", x_dev_role=None, db=db)
    )

    assert result["id"] == user_id
    assert result["username"] == "regular_user"
    assert result["role"] == "user"
    assert result["is_dev_user"] is True


def test_uuid_token_returns_404_when_user_missing(monkeypatch):
    _enable_test_mode(monkeypatch)
    missing_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    db = _FakeDB(_FakeUsersTable())
    monkeypatch.setattr(auth, "get_db", lambda: db)

    with pytest.raises(HTTPException, match="Dev user not found") as exc:
        import asyncio

        asyncio.run(
            auth.parse_dev_token(authorization=f"Bearer dev-token-{missing_id}", x_dev_role=None, db=db)
        )

    assert exc.value.status_code == 404


def test_role_token_creates_dev_user_when_missing(monkeypatch):
    _enable_test_mode(monkeypatch)
    users_table = _FakeUsersTable(users_by_username={})
    db = _FakeDB(users_table)
    monkeypatch.setattr(auth, "get_db", lambda: db)

    import asyncio

    result = asyncio.run(
        auth.parse_dev_token(authorization="Bearer dev-token-admin", x_dev_role=None, db=db)
    )

    assert result["username"] == "dev_admin"
    assert result["role"] == "admin"
    assert result["is_dev_user"] is True
    assert len(users_table.inserted_rows) == 1
    assert users_table.inserted_rows[0]["username"] == "dev_admin"


def test_x_dev_role_takes_priority_over_authorization_header(monkeypatch):
    _enable_test_mode(monkeypatch)
    existing = {
        "id": "f2a8f7bf-0ae5-4694-9c52-fb9df6e86f18",
        "username": "dev_moderator",
        "email": "dev-moderator@a11yhood.test",
        "role": "moderator",
    }
    users_table = _FakeUsersTable(users_by_username={"dev_moderator": existing})
    db = _FakeDB(users_table)
    monkeypatch.setattr(auth, "get_db", lambda: db)

    import asyncio

    result = asyncio.run(
        auth.parse_dev_token(
            authorization="Bearer dev-token-admin",
            x_dev_role="moderator",
            db=db,
        )
    )

    assert result["id"] == existing["id"]
    assert result["username"] == "dev_moderator"
    assert result["role"] == "moderator"
