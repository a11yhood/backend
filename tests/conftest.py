import logging
import os
import subprocess
from pathlib import Path

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

from .test_data import TEST_PRODUCTS, TEST_USERS


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

from config import get_settings
from database_adapter import DatabaseAdapter


def _assert_git_setup() -> None:
    """Fail fast when git is unavailable or repository metadata is inaccessible."""
    project_root = Path(__file__).resolve().parents[1]
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True, text=True)
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        if inside.stdout.strip() != "true":
            raise RuntimeError("git rev-parse did not report an active work tree")
        subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        raise RuntimeError(
            "Git is not set up correctly for tests. "
            "Ensure git is installed and this directory is a valid repository."
        ) from exc


@pytest.fixture(scope="session", autouse=True)
def require_git_setup():
    """Require a healthy git setup before any tests execute."""
    _assert_git_setup()


def _has_usable_supabase(settings) -> bool:
    """Return True when Supabase credentials are present and not placeholders."""
    url = settings.SUPABASE_URL or ""
    key = settings.SUPABASE_KEY or ""

    # Unit-only CI runs provide placeholder values so app import succeeds,
    # but DB-dependent fixtures should still be skipped.
    using_placeholder_url = "placeholder.supabase.co" in url

    return bool(url and key and not using_placeholder_url)


def _require_supabase(settings):
    """Skip DB-dependent tests if Supabase credentials are not configured."""
    if not _has_usable_supabase(settings):
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

    if not _has_usable_supabase(test_settings):
        print("\n✓ Skipping test database reset (Supabase not configured for this run)")
        return

    _require_supabase(test_settings)
    test_db = DatabaseAdapter(test_settings)
    _reset_and_assert_clean(test_db)
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


def _table_row_count(db, table_name: str) -> int:
    """Return exact row count for a table using Supabase count metadata."""
    resp = db.table(table_name).select("*", count="exact").limit(1).execute()
    return resp.count or 0


def _reset_and_assert_clean(db):
    """Reset tables and fail loudly if any key table still has rows."""
    db.cleanup()

    tables_must_be_empty = [
        "products",
        "users",
        "ratings",
        "discussions",
        "collections",
        "scraping_logs",
        "oauth_configs",
        "supported_sources",
        "scraper_search_terms",
        "product_urls",
        "product_tags",
        "product_editors",
        "collection_products",
    ]

    leftovers = {}
    for table in tables_must_be_empty:
        count = _table_row_count(db, table)
        if count != 0:
            leftovers[table] = count

    if leftovers:
        detail = ", ".join(f"{name}={count}" for name, count in leftovers.items())
        raise RuntimeError(
            "Test DB reset failed: tables still contain rows after cleanup: " + detail
        )


def _assert_seed_baseline(db):
    """Fail fast if baseline seed data was not inserted as expected."""
    supported_sources_count = _table_row_count(db, "supported_sources")
    users_count = _table_row_count(db, "users")
    products_count = _table_row_count(db, "products")

    if supported_sources_count < 3:
        raise RuntimeError(
            "Test seed failed: expected at least 3 supported_sources rows, "
            f"found {supported_sources_count}"
        )
    if users_count < len(TEST_USERS):
        raise RuntimeError(
            "Test seed failed: expected at least "
            f"{len(TEST_USERS)} users rows, found {users_count}"
        )
    if products_count < len(TEST_PRODUCTS):
        raise RuntimeError(
            "Test seed failed: expected at least "
            f"{len(TEST_PRODUCTS)} products rows, found {products_count}"
        )


@pytest.fixture
def clean_database(test_db):
    """Provide a freshly cleaned and re-seeded database for each test."""
    _reset_and_assert_clean(test_db)
    _seed_test_data(test_db)
    _assert_seed_baseline(test_db)
    yield test_db


def _seed_test_data(db):
    """
    Insert baseline test data into the Supabase test instance.

    Uses fixed user roles so role-based dev-token auth works consistently.
    Insert/upsert failures should fail fast so fixture corruption is visible.

    Includes:
    - supported_sources (minimal canonical set used by validation and filters)
    - users/products (fixed IDs and deterministic baseline entities)
    - scraper_search_terms (from seed_scraper_search_terms.py; enables scraper tests)

    Intentionally excludes oauth_configs and collections. Tests assert behavior when those
    tables begin empty and create rows explicitly via dedicated fixtures.
    """
    from services.id_generator import normalize_to_snake_case

    # Supported sources (needed for URL validation) — single bulk insert
    supported_sources = [
        {"domain": "ravelry.com", "name": "Ravelry"},
        {"domain": "github.com", "name": "Github"},
        {"domain": "thingiverse.com", "name": "Thingiverse"},
    ]
    db.table("supported_sources").insert(supported_sources).execute()

    # Scraper search terms — flatten to a list and bulk upsert in one call
    # (kept aligned with seed_scripts/seed_scraper_search_terms.py)
    flat_terms = [
        {"platform": platform, "search_term": term}
        for platform, terms in [
            (
                "github",
                [
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
            ),
            (
                "thingiverse",
                [
                    "accessibility",
                    "assistive+device",
                    "arthritis+grip",
                    "adaptive+tool",
                    "mobility+aid",
                    "tremor+stabilizer",
                    "adaptive+utensil",
                ],
            ),
            (
                "ravelry_pa_categories",
                [
                    "medical-device-access",
                    "medical-device-accessory",
                    "mobility-aid-accessory",
                    "other-accessibility",
                    "adaptive",
                    "therapy-aid",
                ],
            ),
        ]
        for term in terms
    ]
    db.table("scraper_search_terms").upsert(
        flat_terms,
        on_conflict="platform,search_term",
    ).execute()

    # Test users with fixed IDs (match DEV_USER_IDS in services/auth.py) — bulk insert
    db.table("users").insert(list(TEST_USERS)).execute()

    # Test products — normalise each row then bulk insert in one call
    products_to_insert = []
    for product in TEST_PRODUCTS:
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
        products_to_insert.append(p)
    db.table("products").insert(products_to_insert).execute()


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
