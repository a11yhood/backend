"""Database access layer providing the Supabase-backed DatabaseAdapter.

Uses Supabase for all environments; configure SUPABASE_URL/KEY in .env or .env.test.
"""

import logging
import time

from fastapi import HTTPException

from config import load_settings_from_env
from database_adapter import DatabaseAdapter, set_supabase_auth_token

db_adapter: DatabaseAdapter | None = None
logger = logging.getLogger(__name__)


def _get_db_adapter() -> DatabaseAdapter:
    """Lazily construct the shared database adapter.

    Unit-only runs may provide placeholder Supabase settings so imports succeed,
    but should not pay the cost of creating a real client unless a test actually
    needs database access.
    """
    global db_adapter

    if db_adapter is None:
        db_adapter = DatabaseAdapter(load_settings_from_env())
        db_adapter.init()

    return db_adapter


def get_db():
    """
    Dependency for FastAPI endpoints to get the Supabase database adapter.

    Usage:
        @app.get("/example")
        def example(db = Depends(get_db)):
            result = db.table('users').select('*').execute()
            return result.data
    """
    return _get_db_adapter()


def wait_for_row_visibility(
    db,
    table_name: str,
    column_name: str,
    value,
    *,
    select: str = "*",
    attempts: int = 5,
    base_delay: float = 0.15,
):
    """Poll until a recently written row becomes query-visible, or return None."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = (
                db.table(table_name)
                .select(select)
                .eq(column_name, value)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                logger.warning(
                    "Visibility probe failed for %s.%s=%r (attempt %d/%d): %s",
                    table_name,
                    column_name,
                    value,
                    attempt,
                    attempts,
                    exc,
                )

        if attempt < attempts:
            time.sleep(base_delay * attempt)

    if last_exc is not None:
        logger.warning(
            "Row visibility probe exhausted for %s.%s=%r after exception: %s",
            table_name,
            column_name,
            value,
            last_exc,
        )
    return None


def verify_token(token: str, adapter: DatabaseAdapter | None = None):
    """Verify a Supabase JWT using the adapter's Supabase client.

    Raises HTTPException 500 if Supabase isn't configured, 401 on auth failure.
    Returns the Supabase user object on success.
    """
    db = adapter or _get_db_adapter()
    supabase_client = getattr(db, "supabase", None)
    if supabase_client is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase client unavailable; ensure SUPABASE_URL/SUPABASE_KEY are configured",
        )

    try:
        user = supabase_client.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Make the JWT available for RLS in downstream queries (if needed)
    set_supabase_auth_token(token)
    if hasattr(db, "set_request_auth_token"):
        db.set_request_auth_token(token)

    return getattr(user, "user", user)
