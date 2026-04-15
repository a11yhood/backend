#!/usr/bin/env bash
set -euo pipefail

DB_CONTAINER="a11yhood-export-verify-pg"
PUBLIC_DB_NAME="a11yhood_restore_public"
PRIVATE_DB_NAME="a11yhood_restore_private"
SINGLE_DB_NAME="a11yhood_restore_single"

SCHEMA_FILE="supabase-schema.sql"
PUBLIC_EXPORT="supabase/public-products.sql"
PRIVATE_EXPORT="supabase/full-database.sql"

cleanup() {
  docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 || true
}

run_psql() {
  local db_name="$1"
  shift
  docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d "$db_name" "$@"
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/db-export/verify_restore_local.sh
  bash scripts/db-export/verify_restore_local.sh <export-file>

Without arguments:
  Verifies the default public and private exports.

With one export file:
  Verifies that single export by restoring it into a throwaway local Postgres database.
  Supported inputs include public, private, test, and seed SQL exports.
EOF
}

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    echo "Missing file: $file_path"
    exit 1
  fi
}

start_container() {
  echo "Starting local Postgres container..."
  cleanup
  docker run --name "$DB_CONTAINER" \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=postgres \
    -d postgres:16 >/dev/null

  for _ in {1..30}; do
    if docker exec "$DB_CONTAINER" pg_isready -U postgres -d postgres >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for Postgres container to become ready"
  exit 1
}

create_database() {
  local db_name="$1"
  echo "Creating verification database: ${db_name}"
  docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d postgres <<SQL >/dev/null
DROP DATABASE IF EXISTS ${db_name};
CREATE DATABASE ${db_name};
SQL
}

load_baseline_objects() {
  local db_name="$1"

  echo "Loading baseline Supabase compatibility objects into ${db_name}..."
  run_psql "$db_name" <<'SQL' >/dev/null
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role;
  END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULL::uuid;
$$;

CREATE OR REPLACE FUNCTION auth.role()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT 'service_role'::text;
$$;

CREATE TABLE IF NOT EXISTS storage.buckets (
  id text PRIMARY KEY,
  name text,
  public boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS storage.objects (
  id uuid,
  bucket_id text,
  name text,
  owner uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
SQL
}

apply_schema() {
  local db_name="$1"
  echo "Applying schema to ${db_name}..."
  docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d "$db_name" < "$SCHEMA_FILE" >/dev/null
}

apply_export() {
  local db_name="$1"
  local export_file="$2"
  echo "Applying export ${export_file} to ${db_name}..."
  docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d "$db_name" < "$export_file" >/dev/null
}

detect_export_kind() {
  local export_file="$1"
  local header
  header=$(head -20 "$export_file")

  case "$header" in
    *"TEST DATABASE EXPORT"*)
      echo "test"
      ;;
    *"Public products dataset"*)
      echo "public"
      ;;
    *"PRIVATE FULL DATABASE EXPORT"*)
      echo "private"
      ;;
    *)
      case "$export_file" in
        *public-products.sql)
          echo "public"
          ;;
        *full-database.sql)
          echo "private"
          ;;
        *seed-test.sql|*seed.sql)
          echo "test"
          ;;
        *)
          echo "unknown"
          ;;
      esac
      ;;
  esac
}

extract_valid_sources() {
  local export_file="$1"
  local scraping_log_lines

  scraping_log_lines=$(grep "INSERT INTO scraping_logs" "$export_file" || true)
  if [[ -z "$scraping_log_lines" ]]; then
    return 0
  fi

  printf '%s\n' "$scraping_log_lines" \
    | cut -d"'" -f6 \
    | sort -u \
    | sed "s/^/'/;s/$/'/" \
    | paste -sd, -
}

update_scraping_logs_constraint() {
  local db_name="$1"
  local export_file="$2"
  local valid_sources

  valid_sources=$(extract_valid_sources "$export_file")
  if [[ -z "$valid_sources" ]]; then
    return 0
  fi

  echo "Updating scraping_logs source constraint with live values: $valid_sources"
  run_psql "$db_name" <<SQL >/dev/null
ALTER TABLE scraping_logs DROP CONSTRAINT IF EXISTS scraping_logs_source_check;
ALTER TABLE scraping_logs ADD CONSTRAINT scraping_logs_source_check
  CHECK (source IN ($valid_sources));
SQL
}

verify_public_restore() {
  local db_name="$1"

  echo "Checking public restore integrity..."
  run_psql "$db_name" <<'SQL'
DO $$
DECLARE
  leaked_rows integer;
BEGIN
  SELECT COUNT(*) INTO leaked_rows FROM users;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked users rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM product_editors;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked product_editors rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM blog_posts;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked blog_posts rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM user_activities;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked user_activities rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM user_requests;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked user_requests rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM collections;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked collections rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM discussions;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked discussions rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM oauth_configs;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked oauth_configs rows: %', leaked_rows;
  END IF;

  SELECT COUNT(*) INTO leaked_rows FROM scraping_logs;
  IF leaked_rows <> 0 THEN
    RAISE EXCEPTION 'public restore leaked scraping_logs rows: %', leaked_rows;
  END IF;
END
$$;

SELECT
  (SELECT COUNT(*) FROM valid_categories) AS valid_categories,
  (SELECT COUNT(*) FROM supported_sources) AS supported_sources,
  (SELECT COUNT(*) FROM tags) AS tags,
  (SELECT COUNT(*) FROM products) AS products,
  (SELECT COUNT(*) FROM product_urls) AS product_urls,
  (SELECT COUNT(*) FROM product_tags) AS product_tags;
SQL
}

verify_private_restore() {
  local db_name="$1"

  echo "Checking private restore integrity..."
  run_psql "$db_name" <<'SQL'
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM product_editors pe
    LEFT JOIN products p ON p.id = pe.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_editors.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM product_editors pe
    LEFT JOIN users u ON u.id = pe.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_editors.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM product_urls pu
    LEFT JOIN products p ON p.id = pu.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_urls.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM product_urls pu
    LEFT JOIN users u ON u.id = pu.created_by
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_urls.created_by rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM product_tags pt
    LEFT JOIN products p ON p.id = pt.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_tags.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM product_tags pt
    LEFT JOIN tags t ON t.id = pt.tag_id
    WHERE t.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned product_tags.tag_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM ratings r
    LEFT JOIN products p ON p.id = r.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned ratings.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM ratings r
    LEFT JOIN users u ON u.id = r.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned ratings.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM discussions d
    LEFT JOIN products p ON p.id = d.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned discussions.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM discussions d
    LEFT JOIN users u ON u.id = d.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned discussions.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM discussions d
    LEFT JOIN users u ON u.id = d.blocked_by
    WHERE d.blocked_by IS NOT NULL AND u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned discussions.blocked_by rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM blog_posts bp
    LEFT JOIN users u ON u.id = bp.author_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned blog_posts.author_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM collections c
    LEFT JOIN users u ON u.id = c.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned collections.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM user_activities ua
    LEFT JOIN users u ON u.id = ua.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned user_activities.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM user_activities ua
    LEFT JOIN products p ON p.id = ua.product_id
    WHERE ua.product_id IS NOT NULL AND p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned user_activities.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM user_requests ur
    LEFT JOIN users u ON u.id = ur.user_id
    WHERE u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned user_requests.user_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM user_requests ur
    LEFT JOIN products p ON p.id = ur.product_id
    WHERE ur.product_id IS NOT NULL AND p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned user_requests.product_id rows found';
  END IF;

  IF EXISTS (
    SELECT 1 FROM user_requests ur
    LEFT JOIN users u ON u.id = ur.reviewed_by
    WHERE ur.reviewed_by IS NOT NULL AND u.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned user_requests.reviewed_by rows found';
  END IF;

  IF to_regclass('public.collection_products') IS NOT NULL AND EXISTS (
    SELECT 1 FROM collection_products cp
    LEFT JOIN collections c ON c.id = cp.collection_id
    WHERE c.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned collection_products.collection_id rows found';
  END IF;

  IF to_regclass('public.collection_products') IS NOT NULL AND EXISTS (
    SELECT 1 FROM collection_products cp
    LEFT JOIN products p ON p.id = cp.product_id
    WHERE p.id IS NULL
  ) THEN
    RAISE EXCEPTION 'orphaned collection_products.product_id rows found';
  END IF;
END
$$;

SELECT
  (SELECT COUNT(*) FROM users) AS users,
  (SELECT COUNT(*) FROM products) AS products,
  (SELECT COUNT(*) FROM product_tags) AS product_tags,
  (SELECT COUNT(*) FROM ratings) AS ratings,
  (SELECT COUNT(*) FROM collections) AS collections,
  (SELECT COUNT(*) FROM user_activities) AS user_activities,
  (SELECT COUNT(*) FROM user_requests) AS user_requests,
  (SELECT COUNT(*) FROM scraping_logs) AS scraping_logs;
SQL
}

trap cleanup EXIT

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_file "$SCHEMA_FILE"
start_container

if [[ $# -eq 0 ]]; then
  require_file "$PUBLIC_EXPORT"
  require_file "$PRIVATE_EXPORT"

  create_database "$PUBLIC_DB_NAME"
  create_database "$PRIVATE_DB_NAME"

  load_baseline_objects "$PUBLIC_DB_NAME"
  apply_schema "$PUBLIC_DB_NAME"
  load_baseline_objects "$PRIVATE_DB_NAME"
  apply_schema "$PRIVATE_DB_NAME"

  apply_export "$PUBLIC_DB_NAME" "$PUBLIC_EXPORT"
  verify_public_restore "$PUBLIC_DB_NAME"

  update_scraping_logs_constraint "$PRIVATE_DB_NAME" "$PRIVATE_EXPORT"
  apply_export "$PRIVATE_DB_NAME" "$PRIVATE_EXPORT"
  verify_private_restore "$PRIVATE_DB_NAME"

  echo "Restore verification completed successfully."
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

SINGLE_EXPORT="$1"
require_file "$SINGLE_EXPORT"

EXPORT_KIND=$(detect_export_kind "$SINGLE_EXPORT")
if [[ "$EXPORT_KIND" == "unknown" ]]; then
  echo "Could not determine export type for: $SINGLE_EXPORT"
  echo "Expected a public, private, test, or seed SQL export file."
  exit 1
fi

create_database "$SINGLE_DB_NAME"
load_baseline_objects "$SINGLE_DB_NAME"
apply_schema "$SINGLE_DB_NAME"

if [[ "$EXPORT_KIND" == "public" ]]; then
  apply_export "$SINGLE_DB_NAME" "$SINGLE_EXPORT"
  verify_public_restore "$SINGLE_DB_NAME"
else
  update_scraping_logs_constraint "$SINGLE_DB_NAME" "$SINGLE_EXPORT"
  apply_export "$SINGLE_DB_NAME" "$SINGLE_EXPORT"
  verify_private_restore "$SINGLE_DB_NAME"
fi

echo "Restore verification completed successfully for ${SINGLE_EXPORT} (${EXPORT_KIND})."
