"""Re-seeding must never replace connected tokens or real credentials with placeholders."""

import importlib.util
import os

import pytest

SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "seed_scripts", "seed_oauth_configs.py")


@pytest.fixture(scope="module")
def build_oauth_update():
    spec = importlib.util.spec_from_file_location("seed_oauth_configs", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_oauth_update


PLACEHOLDER_CONFIG = {
    "platform": "ravelry",
    "client_id": "PLACEHOLDER_CLIENT_ID",
    "client_secret": "PLACEHOLDER_CLIENT_SECRET",
    "redirect_uri": "http://localhost:8000/api/scrapers/oauth/ravelry/callback",
    "access_token": None,
    "refresh_token": None,
}


def test_new_platform_gets_full_config(build_oauth_update):
    assert build_oauth_update(None, PLACEHOLDER_CONFIG) == PLACEHOLDER_CONFIG


def test_existing_connected_row_is_left_alone(build_oauth_update):
    existing = {
        "platform": "ravelry",
        "client_id": "real-id",
        "client_secret": "real-secret",
        "redirect_uri": "https://localhost:5174/admin",
        "access_token": "live-token",
        "refresh_token": "live-refresh",
    }

    update = build_oauth_update(existing, PLACEHOLDER_CONFIG)

    assert update == {"platform": "ravelry"}  # nothing that could overwrite real values


def test_real_env_values_still_apply_to_existing_row(build_oauth_update):
    existing = {"platform": "ravelry", "client_id": "PLACEHOLDER_CLIENT_ID", "access_token": None}
    config = {
        **PLACEHOLDER_CONFIG,
        "client_id": "env-id",
        "client_secret": "env-secret",
        "access_token": "env-token",
    }

    update = build_oauth_update(existing, config)

    assert update["client_id"] == "env-id"
    assert update["client_secret"] == "env-secret"
    assert update["access_token"] == "env-token"
    assert "refresh_token" not in update  # not configured, so not written as null
