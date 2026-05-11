"""Dev mode utilities and enforcement functions.

Handles:
- Row count enforcement per table in dev
- Database reset/reseed
- Dev-specific configuration
"""

import logging

from config import load_settings_from_env
from services.database import get_db
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# Tables that shouldn't have row limits (system tables, join tables)
UNLIMITED_TABLES = {
    "auth.users",
    "auth.sessions",
    "collection_products",
    "user_roles",
}


async def enforce_dev_row_limits():
    """
    Check if any table exceeds dev row limit.
    Raises error if limit is exceeded.

    Only runs in dev mode.
    """
    settings = load_settings_from_env()
    if not settings.TEST_MODE:
        return

    max_rows = settings.DEV_MODE_MAX_ROWS_PER_TABLE
    db = get_db()

    # List of important tables to check
    tables_to_check = [
        "products",
        "users",
        "ratings",
        "discussions",
        "collections",
        "scraping_logs",
        "oauth_configs",
    ]

    over_limit = []
    for table in tables_to_check:
        try:
            resp = db.table(table).select("id", count="exact").execute()
            count = resp.count or 0
            if count > max_rows:
                over_limit.append(f"{table}: {count}/{max_rows}")
        except Exception as e:
            logger.warning(f"Could not count rows in {table}: {e}")

    if over_limit:
        msg = f"Dev row limits exceeded (max {max_rows}):\n" + "\n".join(
            f"  - {item}" for item in over_limit
        )
        logger.warning(msg)
        raise ValueError(msg)


async def reset_database():
    """
    Reset database to a clean state.
    Clears configured tables and returns details about the rows deleted.

    ⚠️ DANGEROUS - Only available in dev mode

    Returns:
        Dict with reset status and cleared row counts
    """

    settings = load_settings_from_env()
    #Check if Test Data Mutation is properly enable
    if not settings.TEST_MODE:
        raise PermissionError("Database reset only available in dev mode")
    _assert_safe_test_environment(settings)

    db = get_db()

    # Use the atomic TRUNCATE RPC function
    # (migrations/test_only/20260415_dev_truncate_all_tables.sql).
    # This lets Postgres handle FK ordering and is safe from partial-clear bugs.
    try:
        resp = db.rpc("dev_truncate_all_tables").execute()
        result = resp.data
        logger.info(
            f"Database reset via RPC. "
            f"total_rows_deleted={result.get('total_rows_deleted', '?')}"
        )
        return result
    except Exception as e:
        # RPC function not yet applied to this environment — fall back to table-by-table delete.
        logger.warning(
            f"dev_truncate_all_tables RPC unavailable ({e}); "
            "falling back to table-by-table delete. "
            "Apply migrations/test_only/20260415_dev_truncate_all_tables.sql "
            "to eliminate this path."
        )

    # Fallback: delete in FK dependency order (children before parents).
    clear_order = [
        "product_tags", "product_editors", "product_urls",
        "scraping_logs", "discussions", "ratings",
        "blog_posts", "user_activities", "user_requests",
        "collection_products", "collections",
        "products", "tags", "oauth_configs", "users",
    ]

    cleared = {}
    errors = {}
    for table in clear_order:
        try:
            resp_before = db.table(table).select("*", count="exact").limit(1).execute()
            count_before = resp_before.count or 0
            if count_before > 0:
                sample_row = resp_before.data[0] if resp_before.data else None
                if not sample_row:
                    logger.warning(f"Unable to sample row from '{table}'; skipping")
                    errors[table] = "unable to sample row"
                    continue
                filter_column = next(iter(sample_row.keys()))
                db.table(table).delete().not_.is_(filter_column, "null").execute()
            cleared[table] = count_before
            logger.info(f"Cleared {table}: {count_before} rows deleted")
        except Exception as table_err:
            logger.error(f"Failed to clear {table}: {table_err}")
            errors[table] = str(table_err)

    logger.info(f"Database reset complete. Cleared: {', '.join(cleared.keys())}")
    result = {
        "status": "reset",
        "cleared_tables": cleared,
        "total_rows_deleted": sum(cleared.values()),
    }
    if errors:
        result["errors"] = errors
        logger.warning(f"Reset completed with errors on: {', '.join(errors.keys())}")
    return result


async def get_dev_stats():
    """Get current dev mode statistics.

    Returns:
        Dict with table row counts and dev configuration
    """
    settings = load_settings_from_env()
    if not settings.TEST_MODE:
        raise PermissionError("Dev stats only available in dev mode")

    db = get_db()
    stats = {
        "mode": "dev",
        "max_rows_per_table": settings.DEV_MODE_MAX_ROWS_PER_TABLE,
        "test_scraper_limit": settings.TEST_SCRAPER_LIMIT,
        "tables": {},
    }

    tables_to_check = [
        "products",
        "users",
        "ratings",
        "discussions",
        "collections",
        "scraping_logs",
        "oauth_configs",
    ]

    for table in tables_to_check:
        try:
            resp = db.table(table).select("id", count="exact").execute()
            count = resp.count or 0
            stats["tables"][table] = {
                "rows": count,
                "at_limit": count >= settings.DEV_MODE_MAX_ROWS_PER_TABLE,
            }
        except Exception as e:
            stats["tables"][table] = {"error": str(e)}

    return stats

def verify_test_token(
    x_test_run_token: str | None = Header(default=None, alias="X-Test-Run-Token")
) -> None:
    """
    FastAPI dependency that verifies the X-Test-Run-Token header.
    Applied to every endpoint in the dev router.
    """
    settings = load_settings_from_env()
    expected_token = settings.DEV_TEST_AUTH_SECRET

    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEV_TEST_AUTH_SECRET is not configured. Set it in your .env file."
        )

    if x_test_run_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Test-Run-Token header."
        )

def _assert_safe_test_environment(settings) -> None:
    """
    Accepts settings as a parameter so the caller controls
    which settings instance is used. Never reassigns settings
    inside this function.
    """
    if not settings.ALLOW_TEST_DATA_MUTATION:
        raise PermissionError(
            "Destructive test operations are disabled.\n"
            "Set ALLOW_TEST_DATA_MUTATION=true in your .env file."
        )

    allowed_refs = [
        r.strip()
        for r in settings.ALLOWED_TEST_PROJECT_REFS.split(",")
        if r.strip()
    ]
    live_ref = _get_live_project_ref()

    if live_ref not in allowed_refs:
        raise PermissionError(
            f"Connected Supabase project '{live_ref}' is not on the test allowlist.\n"
            f"Allowed refs: {allowed_refs}\n"
            "Add this project ref to ALLOWED_TEST_PROJECT_REFS in your .env file."
        )


def assert_test_environment_on_startup(settings) -> None:
    """
    Called once at startup when TEST_MODE is true.
    Crashes the process if the connected database is not a verified
    test database, preventing the server from ever accepting requests
    in a dangerous state.
    """
    try:
        _assert_safe_test_environment(settings)
        logger.info(
            "Test environment verified. Destructive dev routes are active.\n"
            f"  ALLOW_TEST_DATA_MUTATION : true\n"
            f"  Connected project ref    : {_get_live_project_ref()}\n"
        )
    except PermissionError as e:
        raise RuntimeError(
            f"\n{'='*60}\n"
            f"STARTUP BLOCKED: Dev routes are enabled but the database\n"
            f"identity check failed.\n\n"
            f"{e}\n"
            f"{'='*60}\n"
        )
def _get_live_project_ref() -> str:
    """
    Extract the Supabase project ref from the live connection URL.
    The project ref is the subdomain of the Supabase URL.

    Example:
        https://abcdefghijklmnop.supabase.co -> abcdefghijklmnop
    """
    settings = load_settings_from_env()
    url = settings.SUPABASE_URL

    if not url:
        raise RuntimeError(
            "SUPABASE_URL is not configured. Cannot verify project identity."
        )

    try:
        # Strip protocol, take the subdomain before the first dot
        host = url.replace("https://", "").replace("http://", "")
        project_ref = host.split(".")[0]

        if not project_ref:
            raise ValueError("Could not parse project ref from URL")

        return project_ref

    except Exception as e:
        raise RuntimeError(
            f"Failed to extract project ref from SUPABASE_URL '{url}': {e}\n"
            "Expected format: https://your-project-ref.supabase.co"
        )
