"""
Live scraper tests against a running backend, using saved DB credentials.

These tests hit the HTTP API so they can use whatever credentials are
stored in your database (oauth_configs). They require a running server.

Enable with:
  RUN_LIVE_SCRAPERS=1 RUN_AGAINST_SERVER=1 BACKEND_BASE_URL=http://localhost:8000 \
  DEV_USER_ID=<admin_user_id> pytest tests/test_scrapers_live_api.py -v

Alternatively, set ADMIN_TOKEN for real auth:
  RUN_LIVE_SCRAPERS=1 RUN_AGAINST_SERVER=1 BACKEND_BASE_URL=http://localhost:8000 \
  ADMIN_TOKEN=<jwt> pytest tests/test_scrapers_live_api.py -v

Focused Ravelry auth diagnostics (no full scrape):
    RUN_LIVE_SCRAPERS=1 RUN_AGAINST_SERVER=1 BACKEND_BASE_URL=http://localhost:8000 \
    ADMIN_TOKEN=<jwt> pytest tests/test_scrapers_live_api.py::test_ravelry_oauth_debug_health -v

Notes:
- Requires backend TEST_MODE for dev-token path, or a valid admin JWT.
- Uses /api/scrapers/trigger which pulls tokens from oauth_configs.
"""

import logging
import os
import time
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.integration
import httpx
from dotenv import dotenv_values

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

# Keep live test output focused on scraper results rather than per-request noise.
logging.getLogger("httpx").setLevel(logging.WARNING)

if not os.getenv("RUN_LIVE_SCRAPERS") or not os.getenv("RUN_AGAINST_SERVER"):
    pytest.skip(
        "Skipping live API tests without RUN_LIVE_SCRAPERS=1 and RUN_AGAINST_SERVER=1",
        allow_module_level=True,
    )


def _insecure_local_https() -> bool:
    """Allow self-signed HTTPS for localhost targets in live tests."""
    parsed = urlparse(BACKEND_BASE_URL)
    return parsed.scheme == "https" and parsed.hostname in {"localhost", "127.0.0.1"}


def _http_verify_setting() -> bool:
    if _insecure_local_https():
        return False
    return True


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _load_env_file_values() -> dict:
    env_file = os.getenv("ENV_FILE", ".env.test")
    if not os.path.exists(env_file):
        return {}
    return dotenv_values(env_file)


def _ravelry_seed_payload() -> dict | None:
    file_values = _load_env_file_values()

    def pick(*names: str) -> str | None:
        env_values = [os.getenv(name) for name in names]
        file_vals = [file_values.get(name) for name in names]
        return _first_non_empty(*env_values, *file_vals)

    client_id = pick("RAVELRY_APP_KEY")
    client_secret = pick("RAVELRY_APP_SECRET")
    redirect_uri = (
        pick("RAVELRY_REDIRECT_URI") or f"{BACKEND_BASE_URL}/api/scrapers/oauth/ravelry/callback"
    )
    access_token = pick(
        "RAVELRY_ACCESS_TOKEN",
        "RAVELRY_OAUTH_ACCESS_TOKEN",
        "RAVELRY_OAUTH_TOKEN",
        "RAVELRY_TOKEN",
        "RAVELRY_ACCESS",
        "ACCESS_TOKEN_RAVELRY",
        "RAVELRY_TOKEN_VALUE",
        "RAVELRY_AUTH_TOKEN",
        "ACCESS_TOKEN",
    )
    refresh_token = pick(
        "RAVELRY_REFRESH_TOKEN",
        "RAVELRY_OAUTH_REFRESH_TOKEN",
        "RAVELRY_TOKEN_REFRESH",
        "RAVELRY_REFRESH",
        "REFRESH_TOKEN_RAVELRY",
        "RAVELRY_TOKEN_REFRESH_VALUE",
        "RAVELRY_AUTH_REFRESH_TOKEN",
        "REFRESH_TOKEN",
    )

    if not (client_id and client_secret and access_token and refresh_token):
        return None

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def _auth_headers():
    headers = {"Content-Type": "application/json"}
    admin_token = os.getenv("ADMIN_TOKEN")
    dev_user_id = os.getenv("DEV_USER_ID")
    if admin_token:
        headers["Authorization"] = f"Bearer {admin_token}"
    elif dev_user_id:
        headers["Authorization"] = f"dev-token-{dev_user_id}"
    else:
        if _insecure_local_https():
            pytest.skip(
                "No ADMIN_TOKEN/DEV_USER_ID provided for HTTPS backend; set ADMIN_TOKEN for live auth checks"
            )
        # Try to create a temporary admin in TEST_MODE using dev-token
        temp_id = "live-admin-temp-0001"
        # Create user account (no auth required)
        import requests

        put_resp = requests.put(
            f"{BACKEND_BASE_URL}/api/users/{temp_id}",
            json={"username": "live_admin", "email": "live_admin@example.com"},
            verify=_http_verify_setting(),
            timeout=15,
        )
        if put_resp.status_code not in (200, 201):
            pytest.skip("Could not create temp user and no admin token provided")
        # Promote self with dev-token
        patch_resp = requests.patch(
            f"{BACKEND_BASE_URL}/api/users/{temp_id}/role",
            json={"role": "admin"},
            headers={"Authorization": f"dev-token-{temp_id}", "Content-Type": "application/json"},
            verify=_http_verify_setting(),
            timeout=15,
        )
        if patch_resp.status_code != 200:
            pytest.skip("Could not promote temp admin and no admin token provided")
        headers["Authorization"] = f"dev-token-{temp_id}"
    return headers


async def _has_token(client: httpx.AsyncClient, platform: str, headers: dict) -> bool:
    resp = await client.get(
        f"{BACKEND_BASE_URL}/api/scrapers/oauth/{platform}/config", headers=headers
    )
    if resp.status_code != 200:
        return False
    data = resp.json()
    return bool(data.get("has_access_token"))


async def _upsert_ravelry_from_env_if_available(client: httpx.AsyncClient, headers: dict) -> bool:
    """Upsert ravelry oauth config from env/.env.test when values are available.

    Returns True if upsert happened, False if env values were not available.
    """
    payload = _ravelry_seed_payload()
    if not payload:
        return False

    upsert = await client.put(
        f"{BACKEND_BASE_URL}/api/scrapers/oauth-configs/ravelry",
        json=payload,
        headers=headers,
    )
    assert upsert.status_code == 200, upsert.text
    return True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_thingiverse_via_api():
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=120.0, verify=_http_verify_setting()) as client:
        if not await _has_token(client, "thingiverse", headers):
            pytest.skip("No saved Thingiverse token in DB")
        # Trigger real run
        resp = await client.post(
            f"{BACKEND_BASE_URL}/api/scrapers/trigger",
            json={"source": "thingiverse", "test_mode": False},
            headers=headers,
        )
        assert resp.status_code == 200
        # Poll for products
        found = False
        for _ in range(20):
            time.sleep(3)
            pr = await client.get(
                f"{BACKEND_BASE_URL}/api/products",
                params={"origin": "scraped-thingiverse", "limit": 1},
                headers=headers,
            )
            if pr.status_code == 200 and isinstance(pr.json(), list) and len(pr.json()) > 0:
                found = True
                break
        assert found, "Expected Thingiverse products after trigger"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_ravelry_via_api():
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=120.0, verify=_http_verify_setting()) as client:
        # Always prefer fresh env values over stale DB rows when available.
        await _upsert_ravelry_from_env_if_available(client, headers)

        if not await _has_token(client, "ravelry", headers):
            pytest.skip("No saved Ravelry token in DB")

        # Capture latest log id before triggering so we can detect completion for this run.
        prev_logs = await client.get(
            f"{BACKEND_BASE_URL}/api/scrapers/logs",
            params={"source": "ravelry", "limit": 1},
            headers=headers,
        )
        assert prev_logs.status_code == 200
        prev_log_id = prev_logs.json()[0].get("id") if prev_logs.json() else None

        # Trigger test run with limit of 5 items
        resp = await client.post(
            f"{BACKEND_BASE_URL}/api/scrapers/trigger",
            json={"source": "ravelry", "test_mode": True, "test_limit": 5},
            headers=headers,
        )
        assert resp.status_code == 200

        # /trigger runs in background. Poll logs until a new ravelry run appears.
        run_log = None
        # Background scraping can take ~1 minute in live mode; allow extra headroom.
        # Poll every 2s to reduce noisy HTTP logs from the polling loop itself.
        for _ in range(60):
            time.sleep(2)
            logs_resp = await client.get(
                f"{BACKEND_BASE_URL}/api/scrapers/logs",
                params={"source": "ravelry", "limit": 1},
                headers=headers,
            )
            assert logs_resp.status_code == 200
            logs = logs_resp.json()
            if not logs:
                continue
            newest = logs[0]
            if newest.get("id") != prev_log_id:
                run_log = newest
                break

        assert run_log is not None, "Timed out waiting for ravelry scrape log"

        print("\n=== Scrape Result ===")
        print(f"Status: {run_log.get('status', 'unknown')}")
        print(f"Products found: {run_log.get('products_found', 0)}")
        print(f"Products added: {run_log.get('products_added', 0)}")
        print(f"Products updated: {run_log.get('products_updated', 0)}")
        print(f"Duration: {run_log.get('duration_seconds', 0)}s")

        if run_log.get("error_message"):
            print(f"ERROR: {run_log.get('error_message')}")
            pytest.fail(f"Scrape failed: {run_log.get('error_message')}")

        # Confirm test_mode cap: this run should process at most 5 items.
        assert run_log.get("products_found", 0) <= 5, (
            f"Expected 5 or fewer items, got {run_log.get('products_found')}"
        )

        # Fetch latest Ravelry products and print exactly up to 5.
        pr = await client.get(
            f"{BACKEND_BASE_URL}/api/products",
            params={"source": "Ravelry", "limit": 5},
            headers=headers,
        )
        assert pr.status_code == 200
        products = pr.json()

        print(f"\n=== Scraped Products (showing {len(products)} items, max 5) ===")
        for idx, product in enumerate(products, 1):
            print(f"\nProduct {idx}:")
            print(f"  Name: {product.get('name')}")
            print(f"  URL: {product.get('url')}")
            print(f"  Tags: {product.get('tags', [])}")
            print(f"  Description: {product.get('description', '')[:100]}...")

        assert len(products) > 0, "Expected at least one Ravelry product after trigger"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_oauth
async def test_ravelry_oauth_debug_health():
    """Validate current Ravelry OAuth readiness via backend diagnostics endpoint.

    This provides a fast auth sanity check without waiting for a scrape run.
    """
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=30.0, verify=_http_verify_setting()) as client:
        resp = await client.get(
            f"{BACKEND_BASE_URL}/api/scrapers/oauth/ravelry/debug", headers=headers
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()

        # Always upsert from env if available so debug reflects the latest local token fixes.
        upserted = await _upsert_ravelry_from_env_if_available(client, headers)
        if upserted:
            resp = await client.get(
                f"{BACKEND_BASE_URL}/api/scrapers/oauth/ravelry/debug", headers=headers
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()

        # If still missing after optional upsert, skip with actionable guidance.
        if not data.get("has_access_token") or not data.get("has_refresh_token"):
            pytest.skip(
                "Ravelry access/refresh tokens are not configured in env/.env.test; "
                "set RAVELRY_ACCESS_TOKEN and RAVELRY_REFRESH_TOKEN to run this check"
            )

        assert data.get("platform") == "ravelry"
        assert data.get("configured") is True, f"Ravelry OAuth config missing: {data}"
        assert data.get("has_access_token") is True, f"Missing access token: {data}"
        assert data.get("ready_for_refresh") is True, f"Refresh prerequisites missing: {data}"

        # If expiry metadata is present, fail fast on clearly expired tokens.
        if data.get("token_expired") is True:
            raise AssertionError(f"Ravelry token is marked expired: {data}")
