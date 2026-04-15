import os
import logging

logger = logging.getLogger(__name__)

os.environ.setdefault("ENV_FILE", ".env.test")
try:
    from dotenv import load_dotenv
    load_dotenv(os.environ["ENV_FILE"])
except Exception as exc:
    # Optional .env loading for tests; ignore if unavailable but log for diagnostics.
    logger.debug("Failed to load test ENV_FILE %r: %s", os.environ.get("ENV_FILE"), exc)

import pytest
from fastapi.testclient import TestClient
from main import app
from services.database import get_db
from services.auth import get_current_user
from .test_data import TEST_PRODUCTS, TEST_USERS
from datetime import UTC


@pytest.fixture
def client(clean_database):
    """Test client backed by the test Supabase instance. Auth via Authorization headers."""
    app.dependency_overrides[get_db] = lambda: clean_database
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(clean_database, test_user):
    """Test client authenticated as the seeded regular user via UUID dev token."""
    from main import app
    app.dependency_overrides[get_db] = lambda: clean_database
    base_client = TestClient(app)

    class _AuthClient:
        def __init__(self, base, user):
            self._base = base
            self._headers = {"Authorization": f"Bearer dev-token-{user['id']}"}

        def request(self, method, url, **kwargs):
            headers = kwargs.pop("headers", {}) or {}
            merged = {**self._headers, **headers}
            return self._base.request(method, url, headers=merged, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    client = _AuthClient(base_client, test_user)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin_client(clean_database, test_admin):
    """Test client authenticated as the seeded admin user via UUID dev token."""
    from main import app
    app.dependency_overrides[get_db] = lambda: clean_database
    base_client = TestClient(app)

    class _AuthClient:
        def __init__(self, base, user):
            self._base = base
            self._headers = {"Authorization": f"Bearer dev-token-{user['id']}"}

        def request(self, method, url, **kwargs):
            headers = kwargs.pop("headers", {}) or {}
            merged = {**self._headers, **headers}
            return self._base.request(method, url, headers=merged, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    client = _AuthClient(base_client, test_admin)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def auth_client_2(clean_database, test_user_2):
    """Test client authenticated as the second test user via UUID dev token."""
    from main import app
    app.dependency_overrides[get_db] = lambda: clean_database
    base_client = TestClient(app)

    class _AuthClient:
        def __init__(self, base, user):
            self._base = base
            self._headers = {"Authorization": f"Bearer dev-token-{user['id']}"}

        def request(self, method, url, **kwargs):
            headers = kwargs.pop("headers", {}) or {}
            merged = {**self._headers, **headers}
            return self._base.request(method, url, headers=merged, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    client = _AuthClient(base_client, test_user_2)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# Database fixtures (Supabase test instance)
# ============================================================================

from database_adapter import DatabaseAdapter
from config import get_settings


def _require_supabase(settings):
    """Skip the test session if Supabase credentials are not configured."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        pytest.skip(
            "SUPABASE_URL and SUPABASE_KEY are required for tests. "
            "Copy .env.test.example to .env.test and fill in your test Supabase credentials."
        )


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(test_settings):
    """
    Session-scoped fixture that resets the test database once at the start of a run.

    Ensures no stale data from a previous session interferes with the current one.
    Skipped when RUN_AGAINST_SERVER=1 (running tests against a live server).
    """
    if os.getenv("RUN_AGAINST_SERVER"):
        print("\n✓ Skipping test database reset (RUN_AGAINST_SERVER=1)")
        return

    _require_supabase(test_settings)
    test_db = DatabaseAdapter(test_settings)
    test_db.cleanup()
    print("\n✓ Test database reset at session start")


@pytest.fixture(scope="session")
def test_settings():
    """Load test environment settings from ENV_FILE (defaults to .env.test)."""
    return get_settings(os.environ.get("ENV_FILE", ".env.test"))


@pytest.fixture(scope="session")
def test_db(test_settings):
    """Supabase test database adapter (session-scoped; cleaned per-test via clean_database)."""
    _require_supabase(test_settings)
    db = DatabaseAdapter(test_settings)
    yield db


@pytest.fixture
def clean_database(test_db):
    """Provide a freshly cleaned and re-seeded database for each test."""
    test_db.cleanup()
    _seed_test_data(test_db)
    yield test_db


def _seed_test_data(db):
    """
    Insert baseline test data into the Supabase test instance.

    Uses fixed user roles so role-based dev-token auth works consistently.
    Inserts are best-effort; errors are silently ignored (data may already exist).

    Includes:
    - supported_sources (minimal canonical set used by validation and filters)
    - users/products (fixed IDs and deterministic baseline entities)
    - scraper_search_terms (from seed_scraper_search_terms.py; enables scraper tests)

    Intentionally excludes oauth_configs and collections. Tests assert behavior when those
    tables begin empty and create rows explicitly via dedicated fixtures.
    """
    from services.id_generator import normalize_to_snake_case

    # Supported sources (needed for URL validation)
    supported_sources = [
        {"domain": "ravelry.com", "name": "Ravelry"},
        {"domain": "github.com", "name": "Github"},
        {"domain": "thingiverse.com", "name": "Thingiverse"},
    ]
    for source in supported_sources:
        try:
            db.table("supported_sources").insert(source).execute()
        except Exception as exc:
            # Best-effort seed; ignore insert errors (data may already exist), but log them.
            logger.debug("Ignoring error seeding supported_source %r: %s", source, exc, exc_info=True)

    # Scraper search terms (kept aligned with seed_scripts/seed_scraper_search_terms.py)
    scraper_search_terms = [
        {
            "platform": "github",
            "search_terms": [
                "assistive technology",
                "screen reader",
                "eye tracking",
                "speech recognition",
                "switch access",
                "alternative input",
                "text-to-speech",
                "voice control",
                "accessibility aid",
                "mobility aid software",
            ],
        },
        {
            "platform": "thingiverse",
            "search_terms": [
                "accessibility",
                "assistive+device",
                "arthritis+grip",
                "adaptive+tool",
                "mobility+aid",
                "tremor+stabilizer",
                "adaptive+utensil",
            ],
        },
        {
            "platform": "ravelry_pa_categories",
            "search_terms": [
                "medical-device-access",
                "medical-device-accessory",
                "mobility-aid-accessory",
                "other-accessibility",
                "adaptive",
                "therapy-aid",
            ],
        },
    ]
    for row in scraper_search_terms:
        platform = row["platform"]
        for term in row["search_terms"]:
            try:
                db.table("scraper_search_terms").upsert(
                    {"platform": platform, "search_term": term},
                    on_conflict="platform,search_term",
                ).execute()
            except Exception as exc:
                logger.debug(
                    "Ignoring error seeding scraper_search_terms %r/%r: %s",
                    platform,
                    term,
                    exc,
                    exc_info=True,
                )

    # Test users with fixed IDs (match DEV_USER_IDS in services/auth.py)
    for user in TEST_USERS:
        try:
            db.table("users").insert(user).execute()
        except Exception as exc:
            # See _seed_test_data docstring: user seed is best-effort and idempotent.
            logger.debug("Ignoring error seeding user %r: %s", user, exc, exc_info=True)

    # Test products
    for product in TEST_PRODUCTS:
        try:
            p = dict(product)
            # Map source_url -> url (Supabase schema uses 'url')
            if "source_url" in p:
                p["url"] = p.pop("source_url")
            # Products require a slug (NOT NULL UNIQUE in Supabase)
            if not p.get("slug"):
                p["slug"] = normalize_to_snake_case(p.get("name", "product"))
            # Products require a description (NOT NULL in Supabase)
            if not p.get("description"):
                p["description"] = p.get("name", "Test product")
            db.table("products").insert(p).execute()
        except Exception as exc:
            # Product seed is also best-effort; log and continue if insert fails.
            logger.debug("Ignoring error seeding product %r: %s", product, exc, exc_info=True)


@pytest.fixture
def test_user(clean_database):
    """Return the seeded regular test user."""
    result = clean_database.table("users").select("*").eq("username", "regular_user").execute()
    if not result.data:
        raise ValueError("Test user not found - _seed_test_data may have failed")
    return result.data[0]


@pytest.fixture
def test_admin(clean_database):
    """Return the seeded admin test user."""
    result = clean_database.table("users").select("*").eq("username", "admin_user").execute()
    if not result.data:
        raise ValueError("Test admin not found - _seed_test_data may have failed")
    return result.data[0]


@pytest.fixture
def test_moderator(clean_database):
    """Create a test moderator user."""
    from uuid import uuid4
    moderator_data = {
        "id": str(uuid4()),
        "github_id": "test-moderator-567",
        "username": "testmoderator",
        "email": "moderator@example.com",
        "display_name": "Test Moderator",
        "role": "moderator",
    }
    result = clean_database.table("users").insert(moderator_data).execute()
    return result.data[0]


@pytest.fixture
def test_user_2(clean_database):
    """Create a second regular test user."""
    from uuid import uuid4
    user_data = {
        "id": str(uuid4()),
        "github_id": "test-user-789",
        "username": "testuser2",
        "email": "test2@example.com",
        "display_name": "Test User 2",
        "role": "user",
    }
    result = clean_database.table("users").insert(user_data).execute()
    return result.data[0]


@pytest.fixture
def test_product(clean_database, test_user):
    """Create a test product owned by the test user."""
    from uuid import uuid4
    from services.id_generator import normalize_to_snake_case

    product_data = {
        "name": "Test Product",
        "description": "A test product for testing",
        "source": "github",
        "type": "Software",
        "url": f"https://github.com/test/test-product-{uuid4()}",
        "slug": f"test-product-{uuid4()}",
        "created_by": test_user["id"],
    }
    result = clean_database.table("products").insert(product_data).execute()
    return result.data[0]


@pytest.fixture
def sqlite_db(clean_database):
    """Alias for clean_database (backwards compatibility)."""
    return clean_database


@pytest.fixture
def auth_headers():
    """Return a factory that builds UUID-based dev token Authorization headers for a user.

    Identity-sensitive tests (ownership, `/api/users/me`) should use this factory so that
    authentication resolves to the exact seeded user rather than a shared role bucket.

    For role-behaviour tests that only care about the role and not the specific identity,
    pass a ``dev-token-<role>`` header directly instead.
    """
    def _make(user: dict):
        user_id = user.get("id")
        if not user_id:
            raise ValueError("auth_headers: user dict must contain 'id'")
        return {"Authorization": f"Bearer dev-token-{user_id}"}
    return _make


@pytest.fixture
def github_oauth_config(clean_database, test_admin):
    """Create a GitHub OAuth config in the test database."""
    config_data = {
        "platform": "github",
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "redirect_uri": "http://localhost:8000/api/scrapers/oauth/github/callback",
    }
    result = clean_database.table("oauth_configs").insert(config_data).execute()
    return result.data[0]


@pytest.fixture
def thingiverse_oauth_config(clean_database, test_admin, test_settings):
    """
    Create Thingiverse OAuth config with real access token.

    Requires THINGIVERSE_APP_ID in .env.test; test is skipped if absent.
    """
    access_token = test_settings.THINGIVERSE_APP_ID
    if not access_token:
        pytest.skip("THINGIVERSE_APP_ID not set in .env.test")

    config_data = {
        "platform": "thingiverse",
        "client_id": access_token,
        "client_secret": "test-secret",
        "redirect_uri": "http://localhost:8000/api/scrapers/oauth/thingiverse/callback",
        "access_token": access_token,
    }
    result = clean_database.table("oauth_configs").insert(config_data).execute()
    return result.data[0]


@pytest.fixture
def ravelry_oauth_config(clean_database, test_admin, test_settings):
    """
    Create Ravelry OAuth config with real credentials.

    Requires RAVELRY_APP_KEY and RAVELRY_APP_SECRET in .env.test; skipped if absent.
    """
    app_key = test_settings.RAVELRY_APP_KEY
    app_secret = test_settings.RAVELRY_APP_SECRET
    if not app_key or not app_secret:
        pytest.skip("RAVELRY_APP_KEY or RAVELRY_APP_SECRET not set in .env.test")

    config_data = {
        "platform": "ravelry",
        "client_id": app_key,
        "client_secret": app_secret,
        "redirect_uri": "http://localhost:8000/api/scrapers/oauth/ravelry/callback",
        "access_token": app_key,
    }
    result = clean_database.table("oauth_configs").insert(config_data).execute()
    return result.data[0]
