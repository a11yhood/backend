"""Account ban/delete endpoints and banned-account enforcement (no database needed)."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers import users
from services import auth

pytestmark = pytest.mark.unit

ADMIN = {"id": "admin-id", "username": "boss", "role": "admin"}


class _AuthError(Exception):
    def __init__(self, status):
        super().__init__(f"auth error {status}")
        self.status = status


def _target(**extra):
    return {"id": "target-id", "username": "target", "role": "user", **extra}


@pytest.fixture
def target(monkeypatch):
    row = _target()
    monkeypatch.setattr(users, "_get_user_by_identifier", lambda db, identifier: row)
    return row


def _delete(db, current_user=ADMIN):
    return asyncio.run(users.delete_user("target", db=db, current_user=current_user))


def _ban(db, banned=True, current_user=ADMIN):
    update = users.BanUpdate(banned=banned, reason="spam")
    return asyncio.run(users.ban_user("target", update, db=db, current_user=current_user))


@pytest.mark.parametrize("action", [_delete, _ban])
def test_non_admin_is_refused(target, action):
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        action(db, current_user={"id": "x", "role": "moderator"})
    assert exc.value.status_code == 403
    db.table.assert_not_called()


@pytest.mark.parametrize("action", [_delete, _ban])
def test_cannot_act_on_yourself(target, action):
    target["id"] = ADMIN["id"]
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        action(db)
    assert exc.value.status_code == 400
    db.table.assert_not_called()


@pytest.mark.parametrize("role", ["admin", "moderator"])
def test_privileged_account_cannot_be_deleted(target, role):
    target["role"] = role
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        _delete(db)
    assert exc.value.status_code == 400
    db.supabase.auth.admin.delete_user.assert_not_called()


def test_admin_cannot_be_banned(target):
    target["role"] = "admin"
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        _ban(db)
    assert exc.value.status_code == 400
    db.table.assert_not_called()


@pytest.mark.parametrize("banned", [True, False])
def test_ban_and_unban_update_row_and_auth(target, banned):
    db = MagicMock()
    result = _ban(db, banned=banned)

    row = db.table.return_value.update.call_args.args[0]
    assert row["banned"] is banned
    assert (row["banned_at"] is not None) is banned
    assert result["auth_updated"] is True
    db.supabase.auth.admin.update_user_by_id.assert_called_once_with(
        "target-id", {"ban_duration": "876000h" if banned else "none"}
    )


def test_delete_removes_auth_identity_before_row(target):
    db = MagicMock()
    result = _delete(db)

    names = [call[0] for call in db.mock_calls]
    assert names.index("supabase.auth.admin.delete_user") < names.index("table().delete")
    assert result["auth_deleted"] is True


def test_delete_keeps_row_when_auth_delete_fails(target):
    db = MagicMock()
    db.supabase.auth.admin.delete_user.side_effect = _AuthError(500)
    with pytest.raises(HTTPException) as exc:
        _delete(db)
    assert exc.value.status_code == 502
    db.table.return_value.delete.assert_not_called()


def test_delete_proceeds_when_there_is_no_auth_identity(target):
    db = MagicMock()
    db.supabase.auth.admin.delete_user.side_effect = _AuthError(404)
    result = _delete(db)

    assert result["auth_deleted"] is False
    db.table.return_value.delete.assert_called_once()


@pytest.mark.parametrize("banned", [True, False])
def test_banned_account_is_rejected_on_authenticated_requests(monkeypatch, banned):
    monkeypatch.setattr(
        auth, "verify_token", lambda token, db: {"id": "target-id", "email": "t@example.com"}
    )
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        _target(banned=banned)
    ]
    call = auth.get_current_user(authorization="Bearer real-jwt", x_dev_role=None, db=db)

    if banned:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(call)
        assert exc.value.status_code == 403
    else:
        assert asyncio.run(call)["id"] == "target-id"
