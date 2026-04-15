#!/usr/bin/env python3
"""Validate export SQL files against schema, privacy rules, and live source counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import dotenv_values

from supabase import create_client

EXPECTED_PUBLIC_TABLES = {
    "valid_categories",
    "supported_sources",
    "tags",
    "products",
    "product_urls",
    "product_tags",
    "ratings",
}

FULL_EXPORT_TABLES = {
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
}

FORBIDDEN_PUBLIC_PRODUCT_COLUMNS = {
    "external_id",
    "external_data",
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
}

FORBIDDEN_PUBLIC_PRODUCT_URL_COLUMNS = {
    "created_by",
}

# Supabase REST currently returns at most 1000 rows per request.
API_PAGE_SIZE = 1000
# Optional cap for validating sampled exports; None means validate full tables.
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
INSERT_RE = re.compile(r"INSERT INTO\s+([\w\.\"]+)\s*\(", re.IGNORECASE)
ROW_COUNT_RE = re.compile(
    r"^\s*--\s+([\w\.\"]+)\s*\((\d+)\s+rows(?:,.*)?\)\s*$",
    re.IGNORECASE,
)
NO_DATA_RE = re.compile(
    r"^\s*--\s+([\w\.\"]+)\s*:\s*No\s+data\s*$",
    re.IGNORECASE,
)
RATINGS_AGG_RE = re.compile(
    r"^\s*--\s+ratings\s*\((\d+)\s+aggregated\s+rows\s+from\s+(\d+)\s+raw\s+ratings\)\s*$",
    re.IGNORECASE,
)
TRUNCATE_RE = re.compile(r"TRUNCATE\s+TABLE\s+([\w\.\"]+)\s+CASCADE", re.IGNORECASE)
INSERT_LINE_RE = re.compile(
    r'^INSERT INTO\s+([\w\.\"]+)\s*\((.*?)\)\s*VALUES\s*\((.*)\);\s*$',
    re.IGNORECASE | re.DOTALL,
)


def parse_expected_schema(schema_sql: str) -> dict[str, list[str]]:
    expected: dict[str, list[str]] = {}
    pattern = re.compile(r"CREATE TABLE\s+([\w\.\"]+)\s*\((.*?)\);", re.IGNORECASE | re.DOTALL)

    for match in pattern.finditer(schema_sql):
        table = normalize_table_name(match.group(1))
        body = match.group(2)
        cols: list[str] = []

        for raw in body.splitlines():
            line = raw.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue

            upper = line.upper()
            if upper.startswith(("PRIMARY KEY", "UNIQUE", "CONSTRAINT", "FOREIGN KEY", "CHECK")):
                continue

            col = line.split()[0].strip('"')
            if col:
                cols.append(col)

        if cols:
            expected[table] = cols

    return expected


def parse_export_inserts(export_sql: str) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}
    pattern = re.compile(r"INSERT INTO\s+([\w\.\"]+)\s*\((.*?)\)\s*VALUES", re.IGNORECASE | re.DOTALL)

    for match in pattern.finditer(export_sql):
        table = normalize_table_name(match.group(1))
        cols = {c.strip().strip('"') for c in match.group(2).split(",") if c.strip()}
        seen.setdefault(table, set()).update(cols)

    return seen


def parse_export_stats(export_sql: str) -> tuple[set[str], dict[str, int], dict[str, int]]:
    tables: set[str] = set()
    insert_counts: dict[str, int] = defaultdict(int)
    comment_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for line in export_sql.splitlines():
        if match := RATINGS_AGG_RE.match(line):
            tables.add("ratings")
            comment_counts["ratings"] = int(match.group(1))
            source_counts["ratings"] = int(match.group(2))
            continue

        if match := ROW_COUNT_RE.match(line):
            table = normalize_table_name(match.group(1))
            tables.add(table)
            comment_counts[table] = int(match.group(2))
            continue

        if match := NO_DATA_RE.match(line):
            table = normalize_table_name(match.group(1))
            tables.add(table)
            comment_counts[table] = 0
            continue

        if match := TRUNCATE_RE.search(line):
            tables.add(normalize_table_name(match.group(1)))

        if match := INSERT_RE.search(line):
            table = normalize_table_name(match.group(1))
            tables.add(table)
            insert_counts[table] += 1

    final_counts = dict(insert_counts)
    final_counts.update(comment_counts)
    return tables, final_counts, source_counts


def split_sql_values(values_sql: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_quote = False
    bracket_depth = 0
    index = 0

    while index < len(values_sql):
        char = values_sql[index]

        if char == "'":
            current.append(char)
            if in_quote and index + 1 < len(values_sql) and values_sql[index + 1] == "'":
                current.append(values_sql[index + 1])
                index += 2
                continue
            in_quote = not in_quote
            index += 1
            continue

        if not in_quote and char == "[":
            bracket_depth += 1
            current.append(char)
            index += 1
            continue

        if not in_quote and char == "]":
            bracket_depth = max(0, bracket_depth - 1)
            current.append(char)
            index += 1
            continue

        if char == "," and not in_quote and bracket_depth == 0:
            tokens.append("".join(current).strip())
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    if current:
        tokens.append("".join(current).strip())

    return tokens


def parse_sql_value(token: str):
    token = token.strip()

    if token.upper() == "NULL":
        return None
    if token in {"TRUE", "true"}:
        return True
    if token in {"FALSE", "false"}:
        return False

    jsonb_suffix = "::jsonb"
    if token.endswith(jsonb_suffix):
        token = token[: -len(jsonb_suffix)].strip()
        if token.startswith("'") and token.endswith("'"):
            token = token[1:-1].replace("''", "'")
        return json.loads(token)

    array_match = re.fullmatch(r"ARRAY\[(.*)\]::([\w\[\]]+)", token, re.DOTALL)
    if array_match:
        inner = array_match.group(1).strip()
        if not inner:
            return []
        return [parse_sql_value(part) for part in split_sql_values(inner)]

    if token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("''", "'")

    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", token):
        return float(token)

    return token


def split_sql_statements(export_sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_quote = False
    index = 0

    while index < len(export_sql):
        char = export_sql[index]
        current.append(char)

        if char == "'":
            if in_quote and index + 1 < len(export_sql) and export_sql[index + 1] == "'":
                current.append(export_sql[index + 1])
                index += 2
                continue
            in_quote = not in_quote
        elif char == ";" and not in_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []

        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


def parse_export_rows(export_sql: str) -> dict[str, list[dict]]:
    rows_by_table: dict[str, list[dict]] = defaultdict(list)

    for statement in split_sql_statements(export_sql):
        match = INSERT_LINE_RE.match(statement)
        if not match:
            continue

        table = normalize_table_name(match.group(1))
        columns = [column.strip().strip('"') for column in match.group(2).split(",")]
        values = split_sql_values(match.group(3))

        if len(columns) != len(values):
            raise ValueError(
                f"failed to parse export row for {table}: column count {len(columns)} != value count {len(values)}"
            )

        row = {column: parse_sql_value(value) for column, value in zip(columns, values)}
        rows_by_table[table].append(row)

    return dict(rows_by_table)


def normalize_table_name(name: str) -> str:
    clean = name.strip().strip('"')
    if clean.startswith("public."):
        clean = clean[7:]
    return clean


def load_connection_values(env_file: str, url_var: str, key_var: str) -> tuple[str | None, str | None]:
    env_values = dotenv_values(env_file) if Path(env_file).exists() else {}
    url = os.getenv(url_var) or env_values.get(url_var) or env_values.get("SUPABASE_URL")
    key = os.getenv(key_var) or env_values.get(key_var) or env_values.get("SUPABASE_KEY")
    return url, key


def build_supabase_client(label: str, env_file: str, url_var: str, key_var: str):
    url, key = load_connection_values(env_file, url_var, key_var)
    if not url or not key:
        raise RuntimeError(
            f"missing credentials for {label} (checked env vars {url_var}/{key_var} and {env_file})"
        )
    return create_client(url, key)


def fetch_all_rows(client, table_name: str, columns: str) -> list[dict]:
    rows = []
    offset = 0

    while True:
        if MAX_ROWS_PER_TABLE is None:
            page_limit = API_PAGE_SIZE
        else:
            if offset >= MAX_ROWS_PER_TABLE:
                break
            remaining = MAX_ROWS_PER_TABLE - offset
            page_limit = min(API_PAGE_SIZE, remaining)

        query = client.table(table_name).select(columns)
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


def fetch_exact_count(client, table_name: str) -> int:
    try:
        response = client.table(table_name).select("*", count="exact").limit(1).execute()
        if getattr(response, "count", None) is not None:
            return int(response.count)
    except TypeError:
        # Some client/response combinations do not provide a count-compatible shape.
        # Fall back to fetching rows and counting them to preserve existing behavior.
        pass

    return len(fetch_all_rows(client, table_name, "*"))


def fetch_distinct_count(client, table_name: str, column_name: str) -> int:
    rows = fetch_all_rows(client, table_name, column_name)
    return len({row[column_name] for row in rows if row.get(column_name) is not None})


def normalize_value_for_compare(value):
    if isinstance(value, dict):
        return {key: normalize_value_for_compare(val) for key, val in sorted(value.items())}
    if isinstance(value, list):
        return [normalize_value_for_compare(item) for item in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\n")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_row_hash(row: dict, columns: list[str]) -> str:
    payload = {
        column: normalize_value_for_compare(row.get(column))
        for column in sorted(columns)
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_column_invariants(rows: list[dict], columns: list[str]) -> dict[str, dict[str, object]]:
    invariants: dict[str, dict[str, object]] = {}

    for column in columns:
        values = [normalize_value_for_compare(row.get(column)) for row in rows]
        non_null = [value for value in values if value is not None]
        invariant: dict[str, object] = {
            "nulls": len(values) - len(non_null),
            "distinct": len({json.dumps(value, sort_keys=True, default=str) for value in non_null}),
        }

        if non_null and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_null):
            invariant["min"] = min(non_null)
            invariant["max"] = max(non_null)
            invariant["sum"] = round(sum(float(value) for value in non_null), 6)
        elif non_null and column.endswith("_at"):
            timestamp_values = [str(value) for value in non_null]
            invariant["min"] = min(timestamp_values)
            invariant["max"] = max(timestamp_values)

        invariants[column] = invariant

    return invariants


def validate_hashes_and_invariants(
    label: str,
    client,
    export_rows_by_table: dict[str, list[dict]],
    failures: list[str],
) -> None:
    print(f"{label.title()} hash and invariant check:")

    for table in sorted(export_rows_by_table):
        export_rows = export_rows_by_table[table]
        if not export_rows:
            print(f"  - {table}: skipped (no INSERT rows)")
            continue

        columns = list(export_rows[0].keys())
        live_rows = fetch_all_rows(client, table, ",".join(columns))

        export_hashes = Counter(canonical_row_hash(row, columns) for row in export_rows)
        live_hashes = Counter(canonical_row_hash(row, columns) for row in live_rows)

        print(f"  - {table}: compared {len(export_rows)} exported rows")

        if export_hashes != live_hashes:
            missing_hashes = sum((live_hashes - export_hashes).values())
            extra_hashes = sum((export_hashes - live_hashes).values())
            failures.append(
                f"{label} hash mismatch for {table}: export extra rows={extra_hashes}, live missing rows={missing_hashes}"
            )

        export_invariants = build_column_invariants(export_rows, columns)
        live_invariants = build_column_invariants(live_rows, columns)

        mismatched_columns = [
            column for column in columns if export_invariants[column] != live_invariants[column]
        ]
        if mismatched_columns:
            sample_columns = mismatched_columns[:3]
            details = "; ".join(
                f"{column}: export={export_invariants[column]} live={live_invariants[column]}"
                for column in sample_columns
            )
            failures.append(
                f"{label} invariant mismatch for {table} in {len(mismatched_columns)} columns: {details}"
            )


def validate_live_counts(
    label: str,
    client,
    expected_tables: set[str],
    export_counts: dict[str, int],
    source_counts: dict[str, int],
    expected_columns: dict[str, list[str]],
    failures: list[str],
) -> None:
    print(f"{label.title()} live count check:")

    for table in sorted(expected_tables):
        export_count = export_counts.get(table)
        if export_count is None:
            failures.append(f"{label} export missing row count metadata for {table}")
            continue

        if label == "public" and table == "ratings":
            raw_rows = fetch_all_rows(client, "ratings", "product_id,rating")
            live_count = len({row["product_id"] for row in raw_rows if row.get("product_id") is not None})
            raw_live_count = len(raw_rows)
            raw_export_count = source_counts.get("ratings")
            print(
                f"  - ratings aggregated products: export={export_count}, live={live_count}; "
                f"raw source ratings: export={raw_export_count}, live={raw_live_count}"
            )
            if export_count != live_count:
                failures.append(
                    f"public export count mismatch for ratings aggregated products: export has {export_count}, live has {live_count}"
                )
            if raw_export_count is None:
                failures.append("public export missing raw ratings source count metadata")
            elif raw_export_count != raw_live_count:
                failures.append(
                    f"public export raw ratings mismatch: export metadata has {raw_export_count}, live has {raw_live_count}"
                )
            continue

        live_count = len(fetch_all_rows(client, table, "*"))
        print(f"  - {table}: export={export_count}, live={live_count}")
        if export_count != live_count:
            failures.append(
                f"{label} export count mismatch for {table}: export has {export_count}, live has {live_count}"
            )


def main() -> int:
    global MAX_ROWS_PER_TABLE

    parser = argparse.ArgumentParser(description="Validate exported SQL against expected schema")
    parser.add_argument("--schema", default="supabase-schema.sql")
    parser.add_argument("--public-export", default="supabase/public-products.sql")
    parser.add_argument("--private-export", default="supabase/full-database.sql")
    parser.add_argument("--prod-env-file", default=".env")
    parser.add_argument("--skip-live-counts", action="store_true")
    parser.add_argument("--skip-value-checks", action="store_true")
    parser.add_argument(
        "--max-rows-per-table",
        type=int,
        default=None,
        help="Optional row cap per table when validating sampled exports; default validates full tables",
    )
    args = parser.parse_args()

    MAX_ROWS_PER_TABLE = args.max_rows_per_table

    schema_path = Path(args.schema)
    public_path = Path(args.public_export)
    private_path = Path(args.private_export)

    if not schema_path.exists():
        print(f"FAIL: schema file missing: {schema_path}")
        return 1

    expected = parse_expected_schema(schema_path.read_text())
    failures: list[str] = []

    print(f"Expected baseline tables: {len(expected)}")

    public_counts: dict[str, int] = {}
    public_source_counts: dict[str, int] = {}
    public_rows_by_table: dict[str, list[dict]] = {}
    if public_path.exists():
        public_sql = public_path.read_text()
        public_seen = parse_export_inserts(public_sql)
        public_rows_by_table = parse_export_rows(public_sql)
        public_tables, public_counts, public_source_counts = parse_export_stats(public_sql)
        missing = sorted(EXPECTED_PUBLIC_TABLES - public_tables)
        extra = sorted(public_tables - EXPECTED_PUBLIC_TABLES)

        if missing:
            failures.append(f"public export missing expected tables: {missing}")
        if extra:
            failures.append(f"public export has unexpected tables: {extra}")

        leaked = sorted(public_seen.get("products", set()) & FORBIDDEN_PUBLIC_PRODUCT_COLUMNS)
        if leaked:
            failures.append(f"public export leaked forbidden product columns: {leaked}")

        leaked_product_url_columns = sorted(
            public_seen.get("product_urls", set()) & FORBIDDEN_PUBLIC_PRODUCT_URL_COLUMNS
        )
        if leaked_product_url_columns:
            failures.append(
                f"public export leaked forbidden product_url columns: {leaked_product_url_columns}"
            )

        print(f"Public export tables: {len(public_tables)}")
    else:
        failures.append(f"public export missing: {public_path}")

    private_counts: dict[str, int] = {}
    private_rows_by_table: dict[str, list[dict]] = {}
    if private_path.exists():
        private_sql = private_path.read_text()
        private_seen = parse_export_inserts(private_sql)
        private_rows_by_table = parse_export_rows(private_sql)
        private_tables, private_counts, _ = parse_export_stats(private_sql)

        baseline_missing = sorted(t for t in FULL_EXPORT_TABLES if t not in private_tables)
        if baseline_missing:
            failures.append(f"private export missing baseline tables: {baseline_missing[:15]}")

        private_col_missing = []
        for table, exp_cols in expected.items():
            if table in private_seen:
                miss = sorted(set(exp_cols) - private_seen[table])
                if miss:
                    private_col_missing.append((table, miss[:8]))

        if private_col_missing:
            failures.append(f"private export missing expected columns in {len(private_col_missing)} tables")
            for table, cols in private_col_missing[:10]:
                failures.append(f"private export column mismatch: {table} missing {cols}")

        print(f"Private export tables: {len(private_tables)}")
    else:
        failures.append(f"private export missing: {private_path}")

    if not args.skip_live_counts:
        try:
            prod_client = build_supabase_client(
                "production",
                args.prod_env_file,
                "SUPABASE_URL_PROD",
                "SUPABASE_KEY_PROD",
            )
        except RuntimeError as exc:
            failures.append(f"live count validation unavailable: {exc}")
        else:
            if public_path.exists():
                validate_live_counts(
                    "public",
                    prod_client,
                    EXPECTED_PUBLIC_TABLES,
                    public_counts,
                    public_source_counts,
                    expected,
                    failures,
                )
            if private_path.exists():
                validate_live_counts(
                    "private",
                    prod_client,
                    FULL_EXPORT_TABLES,
                    private_counts,
                    {},
                    expected,
                    failures,
                )

            if not args.skip_value_checks:
                if public_path.exists():
                    validate_hashes_and_invariants(
                        "public",
                        prod_client,
                        public_rows_by_table,
                        failures,
                    )
                if private_path.exists():
                    validate_hashes_and_invariants(
                        "private",
                        prod_client,
                        private_rows_by_table,
                        failures,
                    )

    if failures:
        print("\nVALIDATION RESULT: FAIL")
        for issue in failures:
            print(f"- {issue}")
        return 1

    print("\nVALIDATION RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
