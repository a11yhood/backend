"""Who may create a user row through PUT/POST /api/users/{identifier} (no database needed)."""

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers import users

pytestmark = pytest.mark.unit

OWN_ID = str(uuid.uuid4())
CALLER = {"id": OWN_ID, "email": "me@example.com", "role": "user", "github_id": "123"}


@pytest.fixture(autouse=True)
def production_mode(monkeypatch):
    monkeypatch.setattr(users.settings, "TEST_MODE", False)


def _empty_db():
    """A users table with no matching rows that echoes back whatever is inserted."""
    db = MagicMock()
    table = db.table.return_value
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    def insert(row):
        query = MagicMock()
        query.execute.return_value.data = [row]
        return query

    table.insert.side_effect = insert
    return db


def _create(db, identifier, current_user):
    body = users.UserAccountCreate(username="newperson", email="someone-else@example.com")
    return asyncio.run(
        users.create_or_update_user_account(identifier, body, db=db, current_user=current_user)
    )


@pytest.mark.parametrize("identifier", [OWN_ID, str(uuid.uuid4()), "newperson"])
def test_anonymous_caller_cannot_create(identifier):
    db = _empty_db()
    with pytest.raises(HTTPException) as exc:
        _create(db, identifier, None)
    assert exc.value.status_code == 401
    db.table.return_value.insert.assert_not_called()


def test_cannot_create_a_row_for_another_id():
    db = _empty_db()
    with pytest.raises(HTTPException) as exc:
        _create(db, str(uuid.uuid4()), CALLER)
    assert exc.value.status_code == 403
    db.table.return_value.insert.assert_not_called()


@pytest.mark.parametrize("identifier", [OWN_ID, "newperson"])
def test_signed_in_caller_creates_only_their_own_row(identifier):
    db = _empty_db()
    _create(db, identifier, CALLER)

    row = db.table.return_value.insert.call_args.args[0]
    assert row["id"] == OWN_ID
    assert row["role"] == "user"
    assert row["email"] == "me@example.com"
