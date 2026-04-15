"""Database access layer providing the Supabase-backed DatabaseAdapter.

Uses Supabase for all environments; configure SUPABASE_URL/KEY in .env or .env.test.
"""

from fastapi import HTTPException

from config import settings
from database_adapter import DatabaseAdapter, set_supabase_auth_token

# Initialize database adapter using Supabase (configured via .env / .env.test)
db_adapter = DatabaseAdapter(settings)
db_adapter.init()


def get_db():
    """
    Dependency for FastAPI endpoints to get the Supabase database adapter.

    Usage:
        @app.get("/example")
        def example(db = Depends(get_db)):
            result = db.table('users').select('*').execute()
            return result.data
    """
    return db_adapter


def verify_token(token: str, adapter: DatabaseAdapter | None = None):
    """Verify a Supabase JWT using the adapter's Supabase client.

    Raises HTTPException 500 if Supabase isn't configured, 401 on auth failure.
    Returns the Supabase user object on success.
    """
    db = adapter or db_adapter
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
