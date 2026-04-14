#!/usr/bin/env bash
set -euo pipefail

DB_CONTAINER="a11yhood-export-verify-pg"
DB_NAME="a11yhood_restore"

SCHEMA_FILE="supabase-schema.sql"
PUBLIC_EXPORT="supabase/public-products.sql"
TEST_EXPORT="supabase/seed-test.sql"

cleanup() {
  docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 || true
}

trap cleanup EXIT

if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "Missing schema file: $SCHEMA_FILE"
  exit 1
fi

if [[ ! -f "$PUBLIC_EXPORT" ]]; then
  echo "Missing export file: $PUBLIC_EXPORT"
  exit 1
fi

if [[ ! -f "$TEST_EXPORT" ]]; then
  echo "Missing export file: $TEST_EXPORT"
  exit 1
fi

echo "Starting local Postgres container..."
cleanup
docker run --name "$DB_CONTAINER" \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB="$DB_NAME" \
  -d postgres:16 >/dev/null

# Wait until Postgres is ready
for _ in {1..30}; do
  if docker exec "$DB_CONTAINER" pg_isready -U postgres -d "$DB_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "Loading baseline schema..."
docker exec -i "$DB_CONTAINER" psql -U postgres -d "$DB_NAME" <<'SQL' >/dev/null
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

docker exec -i "$DB_CONTAINER" psql -U postgres -d "$DB_NAME" < "$SCHEMA_FILE" >/dev/null || true

echo "Applying public export..."
docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$PUBLIC_EXPORT" >/dev/null

echo "Applying test export..."
docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U postgres -d "$DB_NAME" < "$TEST_EXPORT" >/dev/null

echo "Verifying table row counts after restore..."
docker exec "$DB_CONTAINER" psql -U postgres -d "$DB_NAME" -c "
SELECT
  (SELECT COUNT(*) FROM valid_categories) AS valid_categories,
  (SELECT COUNT(*) FROM supported_sources) AS supported_sources,
  (SELECT COUNT(*) FROM products) AS products,
  (SELECT COUNT(*) FROM scraper_search_terms) AS scraper_search_terms;
"

echo "Restore verification completed successfully."
