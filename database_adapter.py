"""
Database adapter for Supabase.

Always uses Supabase for both production and testing.
Configure SUPABASE_URL/SUPABASE_KEY in .env (production) or .env.test (test instance).
"""

import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Per-request Supabase JWT for RLS-aware queries
_supabase_auth_token: ContextVar[str | None] = ContextVar("supabase_auth_token", default=None)

# Tables that are excluded from dev-mode row-limit checks.
# System tables or pure join tables where a count limit makes no sense.
_ROW_LIMIT_EXEMPT_TABLES = {
    "auth.users",
    "auth.sessions",
    "collection_products",
    "user_roles",
    "supported_sources",
    "scraper_search_terms",
}


def set_supabase_auth_token(token: str | None):
    """Store the active Supabase JWT in a context variable for this request."""
    _supabase_auth_token.set(token)


def get_supabase_auth_token() -> str | None:
    """Retrieve the Supabase JWT for the current request, if set."""
    return _supabase_auth_token.get()


class _RowLimitedTableBuilder:
    """
    Wraps a Supabase table query builder and enforces a row limit on insert operations.

    Used automatically by DatabaseAdapter when TEST_MODE is active and the target table
    is not in _ROW_LIMIT_EXEMPT_TABLES.  Any attempt to insert into a table that is
    already at or above the configured limit raises a ValueError before the insert
    reaches Supabase.
    """

    def __init__(self, builder, supabase_client, table_name: str, max_rows: int):
        self._builder = builder
        self._supabase = supabase_client
        self._table = table_name
        self._max_rows = max_rows

    def insert(self, data, *args, **kwargs):
        """Check row limit, then forward insert to the underlying builder."""
        try:
            resp = self._supabase.table(self._table).select("id", count="exact").execute()
            count = resp.count or 0
        except Exception as exc:
            logger.warning(
                "Row-limit pre-check failed for '%s': %s – proceeding with insert", self._table, exc
            )
            count = 0

        if count >= self._max_rows:
            raise ValueError(
                f"Dev row limit exceeded for table '{self._table}': "
                f"{count}/{self._max_rows} rows. "
                "Use POST /api/dev/reset to clear test data, or increase "
                "DEV_MODE_MAX_ROWS_PER_TABLE in your .env.test."
            )
        return self._builder.insert(data, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._builder, name)


class DatabaseAdapter:
    """
    Database adapter for Supabase.

    Configured via SUPABASE_URL and SUPABASE_KEY.
    Use .env for production, .env.test for the test Supabase instance.
    """

    # Tables to clean during test teardown, ordered so dependents come first.
    _TEST_TABLES_ORDER = [
        # Junction / child tables (no standalone id or CASCADE targets)
        "collection_products",
        "product_tags",
        "product_editors",
        "product_urls",
        "ratings",
        "discussions",
        "user_activities",
        "user_requests",
        "scraping_logs",
        # Parent tables
        "tags",
        "blog_posts",
        "collections",
        "products",
        "users",
        "oauth_configs",
        "supported_sources",
        "scraper_search_terms",
    ]

    _TEST_TABLE_FILTERS = {
        # Composite PK; no standalone id column.
        "collection_products": ("collection_id", "00000000-0000-0000-0000-000000000000"),
        # Normalized search-term rows keep a bigint id in the live schema.
        "scraper_search_terms": ("id", 0),
    }

    def __init__(self, settings=None):
        from config import get_settings

        self.settings = settings or get_settings()
        self._request_auth_token = None
        self.backend = "supabase"  # Always Supabase

        if not self.settings.SUPABASE_URL:
            raise ValueError(
                "SUPABASE_URL must be configured. "
                "Set it in .env (production) or .env.test (test instance)."
            )

        from supabase import create_client

        self.supabase = create_client(
            self.settings.SUPABASE_URL,
            self.settings.SUPABASE_KEY,
        )

    def init(self):
        """No-op: schema is managed via Supabase SQL migrations."""
        pass

    def cleanup(self):
        """Delete all rows from every table (for test isolation).

        Prefers the truncate_test_tables RPC (single round-trip, server-side
        TRUNCATE CASCADE) and falls back to sequential per-table DELETEs if the
        RPC is not yet deployed on the test database.

        Apply migrations/test_only/20260414_add_truncate_test_tables_rpc.sql
        to the test Supabase instance to enable the fast path.

        Uses the service-role key, which bypasses RLS.
        """
        try:
            self.supabase.rpc("truncate_test_tables").execute()
            return
        except Exception as exc:
            logger.debug(
                "truncate_test_tables RPC unavailable, falling back to per-table DELETE: %s",
                exc,
            )
        for table in self._TEST_TABLES_ORDER:
            try:
                column, lower_bound = self._TEST_TABLE_FILTERS.get(
                    table,
                    ("id", "00000000-0000-0000-0000-000000000000"),
                )
                self.supabase.table(table).delete().gte(column, lower_bound).execute()
            except Exception as exc:
                logger.warning("Failed to cleanup table '%s': %s", table, exc)

    def table(self, table_name: str):
        """Return the Supabase table query builder for *table_name*.

        In TEST_MODE, returns a wrapper that raises ValueError on insert if the table
        already holds at least DEV_MODE_MAX_ROWS_PER_TABLE rows.  Tables listed in
        _ROW_LIMIT_EXEMPT_TABLES are always returned unwrapped.
        """
        builder = self.supabase.table(table_name)
        if self.settings.TEST_MODE and table_name not in _ROW_LIMIT_EXEMPT_TABLES:
            return _RowLimitedTableBuilder(
                builder,
                self.supabase,
                table_name,
                self.settings.DEV_MODE_MAX_ROWS_PER_TABLE,
            )
        return builder

    def rpc(self, function_name: str, params: dict = None):
        """Call a Supabase database function (RPC)."""
        return self.supabase.rpc(function_name, params)

    def set_request_auth_token(self, token: str):
        """Store the user JWT for this request (used by some route handlers)."""
        self._request_auth_token = token
