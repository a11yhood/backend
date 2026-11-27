"""Email notifications for user requests.

Provider-neutral ``send_email`` (Brevo REST API first) plus helpers for the two
request events: a new request (notify admins) and a reviewed request (notify the
requester). Sending is best-effort: failures are logged, never raised, so a mail
problem cannot fail the request itself. Call the notify_* helpers from
FastAPI BackgroundTasks.

Security: all user-controlled text is HTML-escaped; emails link to the app instead
of carrying request details; with no provider/key (or in TEST_MODE) nothing is sent.
"""

import html
import logging
import threading
import time
from collections import deque

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT_SECONDS = 10.0

_admin_sent: deque[float] = deque()
_admin_lock = threading.Lock()

_TYPE_LABELS = {
    "moderator": "moderator status",
    "admin": "admin status",
    "product-ownership": "product ownership",
    "source-domain": "a new supported source domain",
    "collection-ownership": "collection ownership",
}


def _clean(value: str | None, limit: int = 200) -> str:
    """Single-line, length-limited text for subjects."""
    return " ".join((value or "").split())[:limit]


def _api_key(s) -> str:
    """Plain-text API key from settings (SecretStr or str); empty if unset."""
    key = s.BREVO_API_KEY
    if key is None:
        return ""
    return key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)


def email_enabled() -> bool:
    s = get_settings()
    return (
        s.EMAIL_PROVIDER == "brevo"
        and bool(_api_key(s))
        and bool(s.EMAIL_FROM)
        and not s.TEST_MODE
    )


def send_email(to: list[str] | str, subject: str, text: str, html_body: str | None = None) -> bool:
    """Send one email. Returns True if the provider accepted it; never raises."""
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r for r in recipients if r and "@" in r]
    if not recipients:
        return False
    if not email_enabled():
        logger.info("Email disabled; not sending %r to %d recipient(s)", _clean(subject), len(recipients))
        return False

    s = get_settings()
    payload = {
        "sender": {"email": s.EMAIL_FROM, "name": s.EMAIL_FROM_NAME},
        "to": [{"email": r} for r in recipients],
        "subject": _clean(subject),
        "textContent": text,
    }
    if html_body:
        payload["htmlContent"] = html_body
    try:
        resp = httpx.post(
            BREVO_SEND_URL,
            json=payload,
            headers={"api-key": _api_key(s), "accept": "application/json"},
            timeout=_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 300:
            logger.error("Brevo rejected email (HTTP %s)", resp.status_code)
            return False
        return True
    except Exception as exc:  # network errors, timeouts: never break the caller
        logger.error("Email send failed: %s", type(exc).__name__)
        return False


def _link(path: str) -> str:
    base = (get_settings().APP_BASE_URL or "").rstrip("/")
    return f"{base}{path}" if base else ""


def _admin_notify_allowed() -> bool:
    """Per-process sliding-hour cap so request spam cannot flood admins."""
    limit = get_settings().EMAIL_ADMIN_NOTIFY_MAX_PER_HOUR
    now = time.monotonic()
    with _admin_lock:
        while _admin_sent and now - _admin_sent[0] > 3600:
            _admin_sent.popleft()
        if len(_admin_sent) >= limit:
            return False
        _admin_sent.append(now)
        return True


def _admin_recipients(db) -> list[str]:
    configured = [e.strip() for e in get_settings().EMAIL_ADMIN_RECIPIENTS.split(",") if e.strip()]
    if configured:
        return configured
    rows = db.table("users").select("email").eq("role", "admin").execute().data or []
    return sorted({r["email"] for r in rows if r.get("email")})


def _user(db, user_id: str) -> dict:
    rows = db.table("users").select("username,email").eq("id", user_id).limit(1).execute().data
    return rows[0] if rows else {}


def notify_admins_of_request(db, request_row: dict) -> bool:
    """Tell admins a new request needs review."""
    try:
        if not email_enabled():
            return False
        if not _admin_notify_allowed():
            logger.warning("Admin notification cap reached; skipping email for request %s", request_row.get("id"))
            return False
        recipients = _admin_recipients(db)
        if not recipients:
            return False
        requester = _user(db, request_row["user_id"])
        label = _TYPE_LABELS.get(request_row.get("type"), "a request")
        name = _clean(requester.get("username"), 60) or "A user"
        url = _link("/requests")
        text = f"{name} submitted a request for {label}.\n" + (f"Review it: {url}\n" if url else "")
        html_body = (
            f"<p>{html.escape(name)} submitted a request for {html.escape(label)}.</p>"
            + (f'<p><a href="{html.escape(url)}">Review requests</a></p>' if url else "")
        )
        return send_email(recipients, f"New a11yhood request: {label}", text, html_body)
    except Exception:
        logger.exception("notify_admins_of_request failed")
        return False


def notify_requester_of_review(db, request_row: dict, status: str) -> bool:
    """Tell the requester their request was approved or rejected."""
    try:
        if not email_enabled():
            return False
        email = _user(db, request_row["user_id"]).get("email")
        if not email:
            logger.info("Requester %s has no email; skipping notification", request_row.get("user_id"))
            return False
        label = _TYPE_LABELS.get(request_row.get("type"), "your request")
        outcome = "approved" if status == "approved" else "not approved"
        url = _link("/requests")
        text = f"Your request for {label} was {outcome}.\n" + (f"Details: {url}\n" if url else "")
        html_body = (
            f"<p>Your request for {html.escape(label)} was {html.escape(outcome)}.</p>"
            + (f'<p><a href="{html.escape(url)}">View your requests</a></p>' if url else "")
        )
        return send_email(email, f"Your a11yhood request was {outcome}", text, html_body)
    except Exception:
        logger.exception("notify_requester_of_review failed")
        return False
