"""Unit tests for the optional CORS_ORIGIN_REGEX allowlist."""
import pytest
from starlette.requests import Request

import main

pytestmark = pytest.mark.unit

PREVIEW_REGEX = r"^https://a11yhood-github-[a-z0-9-]+-a11yhood\.vercel\.app$"
PREVIEW_ORIGIN = "https://a11yhood-github-omclkk0aq-a11yhood.vercel.app"


def _request(origin: str | None) -> Request:
    headers = [(b"origin", origin.encode())] if origin else []
    return Request({"type": "http", "method": "GET", "headers": headers})


def test_regex_unset_returns_none(monkeypatch):
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", "")
    assert main.get_cors_origin_regex() is None


def test_invalid_regex_is_ignored(monkeypatch):
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", "([unclosed")
    assert main.get_cors_origin_regex() is None


def test_preview_origin_allowed_when_regex_matches(monkeypatch):
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "")
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    assert main._request_origin_if_allowed(_request(PREVIEW_ORIGIN)) == PREVIEW_ORIGIN


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "https://a11yhood-github-x-a11yhood.vercel.app.evil.com",
        "http://a11yhood-github-x-a11yhood.vercel.app",
        "https://other-project-x-a11yhood.vercel.app",
    ],
)
def test_non_matching_origin_rejected(monkeypatch, origin):
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "")
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    assert main._request_origin_if_allowed(_request(origin)) is None


def test_preview_origin_rejected_without_regex(monkeypatch):
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "https://localhost:5173")
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", "")
    assert main._request_origin_if_allowed(_request(PREVIEW_ORIGIN)) is None


def test_exact_allowlist_still_works_with_regex_set(monkeypatch):
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "https://localhost:5173/")
    monkeypatch.setattr(main.settings, "CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    assert (
        main._request_origin_if_allowed(_request("https://localhost:5173"))
        == "https://localhost:5173"
    )
