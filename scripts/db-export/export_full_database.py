#!/usr/bin/env python3
"""Export database dumps using a runtime mode flag.

Modes:
    - public: sanitized public products export (no user identifiers)
    - test: full export from test environment
    - private: full export from private/production environment
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

# Add project root to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


TABLES_TO_EXPORT = [
    "valid_categories",
    "supported_sources",
    "tags",
    "users",
    "products",
    "product_editors",
    "product_urls",
    "product_tags",
    "blog_posts",
    "user_activities",
    "user_requests",
    "collections",
    "collection_products",
    "discussions",
    "ratings",
    "scraper_search_terms",
    "oauth_configs",
    "scraping_logs",
]

PUBLIC_TABLES = [
    "valid_categories",
    "supported_sources",
    "tags",
    "products",
    "product_urls",
    "product_tags",
    "ratings",
]

PUBLIC_PRODUCT_COLUMNS = [
    "id",
    "slug",
    "name",
    "type",
    "source",
    "source_url",
    "description",
    "image",
    "image_alt",
    "source_rating",
    "source_rating_count",
    "source_last_updated",
    "created_at",
    "updated_at",
]

PUBLIC_PRODUCT_URL_COLUMNS = [
    "id",
    "product_id",
    "url",
    "description",
    "created_at",
    "updated_at",
]

TEST_TABLE_COLUMNS: dict[str, list[str]] = {
    "products": [
        "id",
        "slug",
        "name",
        "type",
        "source",
        "source_url",
        "external_id",
        "external_data",
        "description",
        "image",
        "image_alt",
        "source_rating",
        "source_rating_count",
        "source_last_updated",
        "scraped_at",
        "created_by",
        "banned",
        "banned_at",
        "banned_by",
        "banned_reason",
        "last_edited_at",
        "last_edited_by",
        "editor_ids",
        "matched_search_terms",
        "created_at",
        "updated_at",
        "computed_rating",
    ],
}

# Supabase REST currently returns at most 1000 rows per request.
API_PAGE_SIZE = 1000
# Optional cap for sampling; None means export full tables.
MAX_ROWS_PER_TABLE: int | None = None

ORDER_COLUMNS: dict[str, list[str]] = {
    "valid_categories": ["category"],
    "supported_sources": ["id"],
    "scraper_search_terms": ["id"],
    "users": ["id"],
    "products": ["id"],
    "product_editors": ["id"],
    "product_urls": ["id"],
    "ratings": ["id"],
    "discussions": ["id"],
    "blog_posts": ["id"],
    "collections": ["id"],
    "collection_products": ["collection_id", "product_id"],
    "user_activities": ["id"],
    "tags": ["id"],
    "product_tags": ["id"],
    "scraping_logs": ["id"],
    "user_requests": ["id"],
    "oauth_configs": ["id"],
}

PRIVATE_COMPLEX_COLUMN_TYPES: dict[str, dict[str, str]] = {
    "products": {
        "external_data": "jsonb",
        "editor_ids": "uuid[]",
        "matched_search_terms": "jsonb",
    },
    "blog_posts": {
        "author_ids": "uuid[]",
        "author_names": "text[]",
        "tags": "text[]",
    },
    "user_activities": {
        "activity_metadata": "jsonb",
    },
}


def _escape_array_element(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _escape_sql_value(
    value: Any, table_name: str | None = None, column_name: str | None = None
) -> str:
    """Escape Python values to SQL format."""
    complex_type = PRIVATE_COMPLEX_COLUMN_TYPES.get(table_name or "", {}).get(column_name or "")

    if value is None:
        return "NULL"
    if complex_type == "jsonb":
        escaped = json.dumps(value, sort_keys=True).replace("'", "''")
        return f"'{escaped}'::jsonb"
    if complex_type and complex_type.endswith("[]"):
        if not value:
            return f"ARRAY[]::{complex_type}"
        return f"ARRAY[{', '.join(_escape_array_element(item) for item in value)}]::{complex_type}"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _escape_public_sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return f"'{json.dumps(value)}'::jsonb"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _fetch_all_rows(db, table_name: str, columns: str = "*") -> list[dict[str, Any]]:
    """Fetch rows from a Supabase table, paging until exhausted or optional cap."""
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        if MAX_ROWS_PER_TABLE is None:
            page_limit = API_PAGE_SIZE
        else:
            if offset >= MAX_ROWS_PER_TABLE:
                break
            remaining = MAX_ROWS_PER_TABLE - offset
            page_limit = min(API_PAGE_SIZE, remaining)

        query = db.table(table_name).select(columns)
        for order_column in ORDER_COLUMNS.get(table_name, []):
            query = query.order(order_column)
        response = query.range(offset, offset + page_limit - 1).execute()
        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)
        if len(batch) < page_limit:
            break

        offset += page_limit

    return rows


def _table_columns_for_mode(table_name: str, export_mode: str) -> str:
    if export_mode == "test" and table_name in TEST_TABLE_COLUMNS:
        return ",".join(TEST_TABLE_COLUMNS[table_name])
    return "*"


def _export_table_data(db, table_name: str, export_mode: str = "private") -> list[str]:
    """Export table as TRUNCATE + INSERT statements."""
    lines = []

    try:
        data = _fetch_all_rows(db, table_name, _table_columns_for_mode(table_name, export_mode))

        lines.append(f"\n-- {table_name} ({len(data)} rows)")

        if not data:
            return lines

        columns = list(data[0].keys())
        lines.append(f"TRUNCATE TABLE {table_name} CASCADE;")

        for row in data:
            values = [
                _escape_sql_value(row.get(col), table_name=table_name, column_name=col)
                for col in columns
            ]
            cols_str = ", ".join(columns)
            vals_str = ", ".join(values)
            lines.append(f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str});")

        return lines

    except Exception as e:
        logger.warning(f"Failed to export {table_name}: {e}")
        return [f"\n-- Failed to export {table_name}: {e}"]


def _export_table_data_public(db, table_name: str) -> list[str]:
    lines = []

    try:
        data = _fetch_all_rows(db, table_name)

        lines.append(f"-- {table_name} ({len(data)} rows)")
        if not data:
            return lines

        columns = list(data[0].keys())
        lines.append(f"TRUNCATE TABLE {table_name} CASCADE;")

        for row in data:
            values = [_escape_public_sql_value(row.get(col)) for col in columns]
            lines.append(
                f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)});"
            )

        lines.append("")
        return lines

    except Exception as e:
        logger.warning(f"Failed to export {table_name}: {e}")
        return [f"-- Failed to export {table_name}: {e}"]


def _export_products_public(db) -> list[str]:
    lines = []

    try:
        data = _fetch_all_rows(db, "products", ",".join(PUBLIC_PRODUCT_COLUMNS))

        lines.append(f"-- products ({len(data)} rows, public columns only)")
        if not data:
            return lines

        lines.append("TRUNCATE TABLE products CASCADE;")

        for row in data:
            values = [_escape_public_sql_value(row.get(col)) for col in PUBLIC_PRODUCT_COLUMNS]
            lines.append(
                f"INSERT INTO products ({', '.join(PUBLIC_PRODUCT_COLUMNS)}) VALUES ({', '.join(values)});"
            )

        lines.append("")
        return lines

    except Exception as e:
        logger.warning(f"Failed to export products: {e}")
        return [f"-- Failed to export products: {e}"]


def _export_product_urls_public(db) -> list[str]:
    lines = []

    try:
        data = _fetch_all_rows(db, "product_urls", ",".join(PUBLIC_PRODUCT_URL_COLUMNS))

        lines.append(f"-- product_urls ({len(data)} rows, public columns only)")
        if not data:
            return lines

        lines.append("TRUNCATE TABLE product_urls CASCADE;")

        for row in data:
            values = [_escape_public_sql_value(row.get(col)) for col in PUBLIC_PRODUCT_URL_COLUMNS]
            lines.append(
                f"INSERT INTO product_urls ({', '.join(PUBLIC_PRODUCT_URL_COLUMNS)}) VALUES ({', '.join(values)});"
            )

        lines.append("")
        return lines

    except Exception as e:
        logger.warning(f"Failed to export product_urls: {e}")
        return [f"-- Failed to export product_urls: {e}"]


def _export_ratings_aggregated(db) -> list[str]:
    lines = []

    try:
        data = _fetch_all_rows(db, "ratings", "product_id,rating")
        aggregated: dict[str, dict[str, float]] = {}

        for row in data:
            product_id = row["product_id"]
            rating = row["rating"]
            if product_id not in aggregated:
                aggregated[product_id] = {"count": 0, "sum": 0}
            aggregated[product_id]["count"] += 1
            aggregated[product_id]["sum"] += rating

        lines.append(f"-- ratings ({len(aggregated)} aggregated rows from {len(data)} raw ratings)")
        lines.append("-- Aggregated into products.computed_rating (no user identifiers)")
        lines.append("")

        if not data:
            return lines

        for product_id, stats in aggregated.items():
            avg_rating = round(stats["sum"] / stats["count"], 2)
            lines.append(
                f"UPDATE products SET computed_rating = {avg_rating} WHERE id = '{product_id}';"
            )

        lines.append("")
        return lines

    except Exception as e:
        logger.warning(f"Failed to export ratings: {e}")
        return [f"-- Failed to export ratings: {e}"]


def _export_public_mode(db) -> tuple[list[str], list[str]]:
    sql_lines = _header_for_mode("public")
    exported_tables: list[str] = []

    logger.info("Exporting public dataset tables...")
    logger.info("  - valid_categories")
    sql_lines.extend(_export_table_data_public(db, "valid_categories"))
    exported_tables.append("valid_categories")

    logger.info("  - supported_sources")
    sql_lines.extend(_export_table_data_public(db, "supported_sources"))
    exported_tables.append("supported_sources")

    logger.info("  - tags")
    sql_lines.extend(_export_table_data_public(db, "tags"))
    exported_tables.append("tags")

    logger.info("  - products (public columns only)")
    sql_lines.extend(_export_products_public(db))
    exported_tables.append("products")

    logger.info("  - product_urls")
    sql_lines.extend(_export_product_urls_public(db))
    exported_tables.append("product_urls")

    logger.info("  - product_tags")
    sql_lines.extend(_export_table_data_public(db, "product_tags"))
    exported_tables.append("product_tags")

    logger.info("  - ratings (aggregated by product)")
    sql_lines.extend(_export_ratings_aggregated(db))
    exported_tables.append("ratings")

    return sql_lines, exported_tables


def _mode_defaults(mode: str) -> tuple[str, str]:
    if mode == "public":
        return ".env", "supabase/public-products.sql"
    if mode == "private":
        return ".env", "supabase/full-database.sql"
    return ".env.test", "supabase/seed-test.sql"


def _header_for_mode(mode: str) -> list[str]:
    if mode == "public":
        return [
            "-- Public products dataset for a11yhood",
            f"-- Generated: {datetime.now().isoformat()}",
            "-- Contains: Products, ratings (aggregated), tags, sources, categories",
            "-- Excludes: User data, authentication, internal metadata",
            "",
        ]

    if mode == "private":
        return [
            "-- ============================================================================",
            "-- 🔒 PRIVATE FULL DATABASE EXPORT - SENSITIVE DATA 🔒",
            "-- ============================================================================",
            f"-- Generated: {datetime.now().isoformat()}",
            "--",
            "-- ⚠️  WARNING: This file contains sensitive data including:",
            "--   • User names and emails",
            "--   • User profiles and preferences",
            "--   • OAuth authentication tokens and configs",
            "--   • Private collections and ratings",
            "--   • Application scraping logs",
            "--   • All internal metadata",
            "--",
            "-- SECURITY REQUIREMENTS:",
            "--   ✓ DO NOT commit to public repositories",
            "--   ✓ DO NOT share with external parties",
            "--   ✓ Store in secure location with access controls",
            "--   ✓ Audit access and maintain logs",
            "--",
            "-- AUTHORIZED USE ONLY:",
            "--   • Organizational backups",
            "--   • Internal database restoration",
            "--   • Team-only database analysis",
            "--   • Disaster recovery procedures",
            "-- ============================================================================",
            "",
        ]

    return [
        "-- TEST DATABASE EXPORT",
        f"-- Generated: {datetime.now().isoformat()}",
        "-- Safe for public sharing: contains only test data",
        "-- Includes: Database schema and all seed data",
        "--",
        "-- Use for:",
        "--   • Developer testing and onboarding",
        "--   • CI/CD pipeline testing",
        "--   • Public repository samples",
        "--   • External contributor setup",
        "",
    ]


def main():
    global MAX_ROWS_PER_TABLE

    parser = argparse.ArgumentParser(
        description="Export database dump for public, test, or private mode"
    )
    parser.add_argument(
        "--mode",
        choices=["public", "test", "private"],
        required=True,
        help="Export mode: public (sanitized), test (shareable full test data), or private (sensitive production data)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output SQL path (defaults by mode)",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Environment file to load (defaults by mode)",
    )
    parser.add_argument(
        "--include-seed-output",
        action="store_true",
        help="Backward-compatible no-op flag used by older test export calls",
    )
    parser.add_argument(
        "--max-rows-per-table",
        type=int,
        default=None,
        help="Optional row cap per table for sample exports; default exports full tables",
    )
    args = parser.parse_args()

    MAX_ROWS_PER_TABLE = args.max_rows_per_table

    default_env, default_output = _mode_defaults(args.mode)
    env_file = args.env_file or default_env
    output_path = args.output or default_output

    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded environment from {env_file}")
    else:
        logger.warning(f"Environment file '{env_file}' not found, using system env")

    from config import get_settings
    from database_adapter import DatabaseAdapter

    try:
        settings = get_settings(env_file)
        db = DatabaseAdapter(settings)
        if args.mode == "private":
            logger.info(f"🔒 PRIVATE DATABASE - Connected to: {settings.SUPABASE_URL}")
        elif args.mode == "public":
            logger.info(f"PUBLIC EXPORT - Connected to: {settings.SUPABASE_URL}")
        else:
            logger.info(f"Connected to Supabase: {settings.SUPABASE_URL}")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        return 1

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    sql_lines = _header_for_mode(args.mode)

    try:
        if args.mode == "private":
            logger.info("⚠️  Exporting SENSITIVE data...")
            exported_tables = []
            for table_name in TABLES_TO_EXPORT:
                try:
                    logger.info(f"  - {table_name}")
                    table_sql = _export_table_data(db, table_name, export_mode=args.mode)
                    if table_sql:
                        sql_lines.extend(table_sql)
                        exported_tables.append(table_name)
                except Exception as e:
                    logger.warning(f"  ⚠ {table_name}: {str(e)}")
                    continue
        elif args.mode == "public":
            sql_lines, exported_tables = _export_public_mode(db)
        else:
            logger.info("Exporting tables...")
            exported_tables = []
            for table_name in TABLES_TO_EXPORT:
                try:
                    logger.info(f"  - {table_name}")
                    table_sql = _export_table_data(db, table_name, export_mode=args.mode)
                    if table_sql:
                        sql_lines.extend(table_sql)
                        exported_tables.append(table_name)
                except Exception as e:
                    logger.warning(f"  ⚠ {table_name}: {str(e)}")
                    continue

        with open(output_path, "w") as f:
            f.write("\n".join(sql_lines))

        file_size = os.path.getsize(output_path)
        if args.mode == "private":
            logger.info(f"✓ Private export complete: {output_path} ({file_size:,} bytes)")
            logger.info(f"  Exported {len(exported_tables)} tables")
            logger.warning("  🔒 This file contains SENSITIVE data - handle with care!")
            logger.warning("  🔒 Do NOT commit to version control or external sources")
        elif args.mode == "public":
            logger.info(f"✓ Public export complete: {output_path} ({file_size:,} bytes)")
            logger.info(f"  Exported {len(exported_tables)} tables")
            logger.info("  Safe to share publicly")
        else:
            logger.info(f"✓ Test database export complete: {output_path} ({file_size:,} bytes)")
            logger.info(f"  Exported {len(exported_tables)} tables")
            logger.info("  Safe to share with developers and use in CI/CD")

        return 0

    except Exception as e:
        logger.error(f"Export failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
