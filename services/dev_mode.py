"""Dev mode utilities and enforcement functions.

Handles:
- Row count enforcement per table in dev
- Database reset/reseed
- Dev-specific configuration
"""

import logging

from config import load_settings_from_env
from services.database import get_db

logger = logging.getLogger(__name__)

SEED_VERSION = "2026-05-15-seed-image-contract-v1"
SEEDED_PRODUCT_SLUG = "test-product"
SEEDED_IMAGE_KEY = "seed:test-product:image:1"
SEEDED_USER_USERNAME = "regular_user"

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
    if not settings.TEST_MODE:
        raise PermissionError("Database reset only available in dev mode")

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


def get_seed_manifest() -> dict:
    """Return stable seeded IDs used by frontend integration tests."""
    db = get_db()

    image_resp = (
        db.table("images")
        .select("id")
        .eq("canonical_key", SEEDED_IMAGE_KEY)
        .limit(1)
        .execute()
    )
    product_resp = (
        db.table("products")
        .select("id,image_id,banned")
        .eq("slug", SEEDED_PRODUCT_SLUG)
        .limit(1)
        .execute()
    )
    user_resp = (
        db.table("users")
        .select("id")
        .eq("username", SEEDED_USER_USERNAME)
        .limit(1)
        .execute()
    )

    seeded_image_id = image_resp.data[0]["id"] if image_resp.data else None
    seeded_product_id = product_resp.data[0]["id"] if product_resp.data else None
    seeded_product_image_id = product_resp.data[0].get("image_id") if product_resp.data else None
    seeded_product_visible = bool(product_resp.data and not product_resp.data[0].get("banned", False))
    seeded_user_id = user_resp.data[0]["id"] if user_resp.data else None

    return {
        "seed_version": SEED_VERSION,
        "seeded_image_id": seeded_image_id,
        "seeded_product_with_image_id": seeded_product_id,
        "seeded_product_image_id": seeded_product_image_id,
        "seeded_product_visible": seeded_product_visible,
        "seeded_user_id": seeded_user_id,
    }


async def reset_and_reseed_database() -> dict:
    """Reset then reseed test data before returning success."""
    reset_result = await reset_database()

    from seed_scripts.seed_all import main as run_seed_all

    seed_exit_code = run_seed_all()
    if seed_exit_code != 0:
        raise RuntimeError(f"Seed process failed with exit code {seed_exit_code}")

    manifest = get_seed_manifest()
    return {
        **reset_result,
        "status": "reset",
        "seeded": True,
        "seed_version": manifest["seed_version"],
        "seed_manifest": manifest,
    }


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
