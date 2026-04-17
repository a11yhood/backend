"""Unit tests for discussion route logic with mocked DB."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.discussions import DiscussionBlockRequest, DiscussionCreate, DiscussionUpdate
from routers import discussions as discussions_router

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeDiscussionsTable:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.inserted = None
        self.updated = None
        self._selected_id = None
        self._selected_parent_id = None
        self._selected_parent_ids = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        if field == "id":
            self._selected_id = value
            self._selected_parent_id = None
        if field == "parent_id":
            self._selected_parent_id = value
            self._selected_id = None
        return self

    def in_(self, field, values):
        if field == "parent_id":
            self._selected_parent_ids = set(values)
        return self

    def insert(self, row):
        self.inserted = row
        return self

    def update(self, row):
        self.updated = row
        return self

    def execute(self):
        if self.inserted is not None:
            row = {"id": "d-new", **self.inserted}
            return _FakeResponse([row])

        if self.updated is not None:
            base = self.existing[0] if self.existing else {"id": self._selected_id}
            row = {**base, **self.updated}
            return _FakeResponse([row])

        if self._selected_parent_ids is not None:
            rows = [r for r in self.existing if r.get("parent_id") in self._selected_parent_ids]
            return _FakeResponse(rows)

        if self._selected_id is not None:
            rows = [r for r in self.existing if r.get("id") == self._selected_id]
            return _FakeResponse(rows)

        if self._selected_parent_id is not None:
            rows = [r for r in self.existing if r.get("parent_id") == self._selected_parent_id]
            return _FakeResponse(rows)

        return _FakeResponse(self.existing)


class _FakeDB:
    def __init__(self, table):
        self._table = table

    def table(self, name: str):
        assert name == "discussions"
        return self._table


def test_create_discussion_sanitizes_content(monkeypatch):
    table = _FakeDiscussionsTable()
    db = _FakeDB(table)
    monkeypatch.setattr(discussions_router, "sanitize_html", lambda value: "clean-content")

    result = asyncio.run(
        discussions_router.create_discussion(
            discussion=DiscussionCreate(product_id="p1", content="<script>x</script>"),
            current_user={"id": "u1", "username": "alice"},
            db=db,
        )
    )

    assert result["content"] == "clean-content"
    assert table.inserted["content"] == "clean-content"
    assert table.inserted["username"] == "alice"


def test_update_discussion_forbidden_for_non_owner():
    discussion_id = str(uuid4())
    table = _FakeDiscussionsTable(existing=[{"id": discussion_id, "user_id": "owner"}])
    db = _FakeDB(table)

    with pytest.raises(HTTPException, match="Not authorized to update") as exc:
        asyncio.run(
            discussions_router.update_discussion(
                discussion_id=discussion_id,
                discussion=DiscussionUpdate(content="new"),
                current_user={"id": "other", "role": "user"},
                db=db,
            )
        )
    assert exc.value.status_code == 403


def test_delete_discussion_forbidden_for_non_owner_non_admin():
    discussion_id = str(uuid4())
    table = _FakeDiscussionsTable(existing=[{"id": discussion_id, "user_id": "owner"}])
    db = _FakeDB(table)

    with pytest.raises(HTTPException, match="Not authorized to delete") as exc:
        asyncio.run(
            discussions_router.delete_discussion(
                discussion_id=discussion_id,
                current_user={"id": "other", "role": "user"},
                db=db,
            )
        )
    assert exc.value.status_code == 403


def test_get_discussion_deleted_leaf_returns_404():
    discussion_id = str(uuid4())
    existing = [{"id": discussion_id, "content": "[deleted]", "parent_id": None}]
    table = _FakeDiscussionsTable(existing=existing)
    db = _FakeDB(table)

    with pytest.raises(HTTPException, match="Discussion not found") as exc:
        asyncio.run(discussions_router.get_discussion(discussion_id=discussion_id, db=db))
    assert exc.value.status_code == 404


def test_block_discussion_requires_admin_or_moderator():
    discussion_id = str(uuid4())
    table = _FakeDiscussionsTable(existing=[{"id": discussion_id, "user_id": "u1"}])
    db = _FakeDB(table)

    with pytest.raises(HTTPException, match="Not authorized to block") as exc:
        asyncio.run(
            discussions_router.block_discussion(
                discussion_id=discussion_id,
                payload=DiscussionBlockRequest(reason="spam"),
                current_user={"id": "u2", "role": "user"},
                db=db,
            )
        )
    assert exc.value.status_code == 403
