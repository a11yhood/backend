"""Dev mode API endpoints - only available in TEST_MODE.

Provides:
- GET /api/dev/stats - Table statistics
- POST /api/dev/reset - Clear all data
- Health check specific to dev
"""

from fastapi import APIRouter, Depends, HTTPException

from config import load_settings_from_env
from services.auth import ensure_admin, get_current_user
from services.dev_mode import enforce_dev_row_limits, get_dev_stats, reset_database

router = APIRouter(prefix="/api/dev", tags=["dev"])


def _require_dev_mode():
    """Verify dev mode is enabled."""
    settings = load_settings_from_env()
    if not settings.TEST_MODE:
        raise HTTPException(status_code=404, detail="Dev endpoints not available outside TEST_MODE")


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    """Get dev mode statistics (admin only).

    Returns:
        - mode: "dev"
        - max_rows_per_table: configured limit
        - scrapers_disabled: whether scheduled scrapers are off
        - test_scraper_limit: max products per scraper run
        - tables: dict of {table_name: {rows: int, at_limit: bool}}
    """
    _require_dev_mode()
    ensure_admin(current_user)

    return await get_dev_stats()


@router.post("/reset")
async def reset_db(current_user: dict = Depends(get_current_user)):
    """
    ⚠️ DANGEROUS: Reset database to clean state.

    - Clears ALL user-created data
    - Only available in dev mode + admin role
    - Does NOT reseed (manually run seed script after)

    Use cases:
    - Cleanup after messy testing
    - Before automated test runs
    - Reset when making schema changes

    Admin only.

    Returns:
        - status: "reset"
        - cleared_tables: dict of {table_name: rows_deleted}
        - total_rows_deleted: int
    """
    _require_dev_mode()
    ensure_admin(current_user)

    return await reset_database()


@router.get("/check-limits")
async def check_limits(current_user: dict = Depends(get_current_user)):
    """
    Check if any table exceeds dev row limits.

    Returns 200 if all tables are within limits.
    Returns 400 with details if any table exceeds limit.

    Admin only.
    """
    _require_dev_mode()
    ensure_admin(current_user)

    try:
        await enforce_dev_row_limits()
        return {"status": "ok", "message": "All tables within dev limits"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health-dev")
async def health_dev():
    """Dev-specific health check - no auth required.

    Confirms:
    - Dev mode is enabled
    - Dev endpoints are available

    Always returns 200 in dev mode.
    """
    _require_dev_mode()
    return {"status": "healthy", "mode": "dev", "message": "Dev mode active - endpoints available"}
