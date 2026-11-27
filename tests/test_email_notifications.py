"""Tests for request email notifications (services/email.py and hooks in routers/requests.py)."""

import pytest
from pydantic import SecretStr

from services import email as email_mod


class _Result:
    def __init__(self, data):
        self.data = data


class FakeDB:
    """Minimal table().select().eq().limit().execute() stand-in."""

    def __init__(self, users):
        self.users = users
        self._filters = {}

    def table(self, name):
        assert name == "users"
        self._filters = {}
        return self

    def select(self, *_):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, _):
        return self

    def execute(self):
        rows = [u for u in self.users if all(u.get(k) == v for k, v in self._filters.items())]
        return _Result(rows)


class FakeSettings:
    EMAIL_PROVIDER = "brevo"
    BREVO_API_KEY = SecretStr("test-key")
    EMAIL_FROM = "notifications@example.org"
    EMAIL_FROM_NAME = "a11yhood"
    EMAIL_ADMIN_RECIPIENTS = ""
    EMAIL_ADMIN_NOTIFY_MAX_PER_HOUR = 20
    APP_BASE_URL = "https://app.example.org"
    TEST_MODE = False


class _Sent(list):
    settings: FakeSettings


@pytest.fixture
def sent(monkeypatch):
    """Enable email with fake settings and capture outgoing provider calls."""
    settings = FakeSettings()
    monkeypatch.setattr(email_mod, "get_settings", lambda: settings)
    email_mod._admin_sent.clear()
    calls = _Sent()

    class Resp:
        status_code = 201

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return Resp()

    monkeypatch.setattr(email_mod.httpx, "post", fake_post)
    calls.settings = settings
    return calls


USERS = [
    {"id": "admin-1", "username": "root", "email": "admin@example.org", "role": "admin"},
    {"id": "admin-2", "username": "root2", "email": None, "role": "admin"},
    {"id": "u1", "username": "alice", "email": "alice@example.org", "role": "user"},
    {"id": "u2", "username": "noemail", "email": None, "role": "user"},
]
REQ = {"id": "r1", "user_id": "u1", "type": "moderator", "reason": "<script>x</script>"}


def test_disabled_by_default_sends_nothing(monkeypatch):
    class Off(FakeSettings):
        EMAIL_PROVIDER = "none"

    monkeypatch.setattr(email_mod, "get_settings", lambda: Off())
    monkeypatch.setattr(email_mod.httpx, "post", lambda *a, **k: pytest.fail("must not send"))
    assert email_mod.send_email("a@b.org", "s", "t") is False
    assert email_mod.notify_admins_of_request(FakeDB(USERS), REQ) is False


def test_test_mode_never_sends(monkeypatch):
    class T(FakeSettings):
        TEST_MODE = True

    monkeypatch.setattr(email_mod, "get_settings", lambda: T())
    monkeypatch.setattr(email_mod.httpx, "post", lambda *a, **k: pytest.fail("must not send"))
    assert email_mod.send_email("a@b.org", "s", "t") is False


def test_admins_notified_only_with_email_addresses(sent):
    assert email_mod.notify_admins_of_request(FakeDB(USERS), REQ) is True
    assert len(sent) == 1
    body = sent[0]["json"]
    assert body["to"] == [{"email": "admin@example.org"}]
    assert sent[0]["headers"]["api-key"] == "test-key"
    assert "https://app.example.org/requests" in body["textContent"]


def test_user_text_is_not_included_or_unescaped(sent):
    db = FakeDB(USERS + [{"id": "u3", "username": "<b>evil</b>", "email": "e@example.org", "role": "user"}])
    email_mod.notify_admins_of_request(db, {**REQ, "user_id": "u3"})
    html_body = sent[0]["json"]["htmlContent"]
    assert "<b>evil</b>" not in html_body
    assert "&lt;b&gt;evil&lt;/b&gt;" in html_body
    assert "<script>" not in html_body  # request reason is never included


def test_admin_recipients_override(sent):
    sent.settings.EMAIL_ADMIN_RECIPIENTS = "team@example.org, ops@example.org"
    email_mod.notify_admins_of_request(FakeDB(USERS), REQ)
    assert [t["email"] for t in sent[0]["json"]["to"]] == ["team@example.org", "ops@example.org"]


def test_admin_notifications_are_rate_limited(sent):
    sent.settings.EMAIL_ADMIN_NOTIFY_MAX_PER_HOUR = 2
    results = [email_mod.notify_admins_of_request(FakeDB(USERS), REQ) for _ in range(4)]
    assert results == [True, True, False, False]
    assert len(sent) == 2


def test_requester_notified_on_approval_and_rejection(sent):
    assert email_mod.notify_requester_of_review(FakeDB(USERS), REQ, "approved") is True
    assert email_mod.notify_requester_of_review(FakeDB(USERS), REQ, "rejected") is True
    assert sent[0]["json"]["to"] == [{"email": "alice@example.org"}]
    assert "approved" in sent[0]["json"]["subject"]
    assert "not approved" in sent[1]["json"]["subject"]


def test_requester_without_email_is_skipped(sent):
    assert email_mod.notify_requester_of_review(FakeDB(USERS), {**REQ, "user_id": "u2"}, "approved") is False
    assert sent == []


def test_provider_error_and_exception_never_raise(sent, monkeypatch):
    class Bad:
        status_code = 500

    monkeypatch.setattr(email_mod.httpx, "post", lambda *a, **k: Bad())
    assert email_mod.send_email("a@b.org", "s", "t") is False

    def boom(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(email_mod.httpx, "post", boom)
    assert email_mod.send_email("a@b.org", "s", "t") is False


@pytest.mark.integration
def test_create_and_review_request_trigger_notifications(
    client, test_user, test_admin, auth_headers, monkeypatch
):
    import routers.requests as req_router

    created, reviewed = [], []
    monkeypatch.setattr(req_router, "notify_admins_of_request", lambda db, row: created.append(row["id"]))
    monkeypatch.setattr(
        req_router, "notify_requester_of_review", lambda db, row, status: reviewed.append((row["id"], status))
    )

    r = client.post(
        "/api/requests/",
        json={"type": "moderator", "reason": "help"},
        headers=auth_headers(test_user),
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert created == [rid]

    r = client.patch(f"/api/requests/{rid}", json={"status": "approved"}, headers=auth_headers(test_admin))
    assert r.status_code == 200
    assert reviewed == [(rid, "approved")]


def test_api_key_is_secret_and_not_in_repr():
    from config import Settings

    s = Settings(_env_file=None, BREVO_API_KEY="super-secret-value")
    assert "super-secret-value" not in repr(s)
    assert "super-secret-value" not in str(s.model_dump())
    assert email_mod._api_key(s) == "super-secret-value"
