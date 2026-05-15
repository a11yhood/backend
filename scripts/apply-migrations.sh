#!/usr/bin/env bash
set -euo pipefail

# Apply SQL migrations in migrations/ to a Supabase/Postgres database.
#
# Defaults:
# - ENV_FILE=.env.test
# - DB URL from SUPABASE_DB_URL, DATABASE_URL, or TEST_DATABASE_URL
#
# Usage:
#   ./scripts/apply-migrations.sh
#   ./scripts/apply-migrations.sh --env-file .env
#   SUPABASE_DB_URL='postgresql://...' ./scripts/apply-migrations.sh

ENV_FILE=".env.test"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="${ROOT_DIR}/migrations"

print_help() {
  cat <<'EOF'
Apply SQL migrations to Supabase/Postgres.

Usage:
  ./scripts/apply-migrations.sh [--env-file PATH] [--help]

Options:
  --env-file PATH   Environment file to read DB URL from (default: .env.test)
  --help            Show this help message

DB URL lookup order:
  1) SUPABASE_DB_URL (shell env)
  2) DATABASE_URL (shell env)
  3) TEST_DATABASE_URL (shell env)
  4) SUPABASE_DB_URL in env file
  5) DATABASE_URL in env file
  6) TEST_DATABASE_URL in env file

Notes:
- Requires psql on PATH.
- Tracks applied migrations in public.schema_migrations.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      if [[ $# -lt 2 ]]; then
        echo "Error: --env-file requires a value" >&2
        exit 1
      fi
      ENV_FILE="$2"
      shift 2
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_help
      exit 1
      ;;
  esac
done

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
  echo "Error: migrations directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "Error: psql is required but not installed." >&2
  echo "Install PostgreSQL client tools, then retry." >&2
  exit 1
fi

read_env_var() {
  local file="$1"
  local key="$2"

  if [[ ! -f "$file" ]]; then
    return 0
  fi

  # Extract first non-comment assignment and trim surrounding whitespace/quotes.
  local line
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | head -n 1 || true)"
  if [[ -z "$line" ]]; then
    return 0
  fi

  local value
  value="${line#*=}"
  value="$(printf '%s' "$value" | sed -E "s/^[[:space:]]+//; s/[[:space:]]+$//; s/^\"(.*)\"$/\1/; s/^'(.*)'$/\1/")"
  printf '%s' "$value"
}

DB_URL="${SUPABASE_DB_URL:-${DATABASE_URL:-${TEST_DATABASE_URL:-}}}"
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(read_env_var "$ROOT_DIR/$ENV_FILE" "SUPABASE_DB_URL")"
fi
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(read_env_var "$ROOT_DIR/$ENV_FILE" "DATABASE_URL")"
fi
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(read_env_var "$ROOT_DIR/$ENV_FILE" "TEST_DATABASE_URL")"
fi

if [[ -z "$DB_URL" ]]; then
  echo "Error: No database URL found." >&2
  echo "Set SUPABASE_DB_URL (recommended) in shell or ${ENV_FILE}," >&2
  echo "or set DATABASE_URL/TEST_DATABASE_URL." >&2
  exit 1
fi

echo "Applying migrations from: $MIGRATIONS_DIR"
echo "Using env file: $ENV_FILE"

echo "Ensuring migration tracking table exists..."
psql "$DB_URL" -v ON_ERROR_STOP=1 -c "
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
" >/dev/null

applied=0
skipped=0
failed=0

while IFS= read -r migration_file; do
  filename="$(basename "$migration_file")"

  exists="$(psql "$DB_URL" -tA -c "SELECT 1 FROM public.schema_migrations WHERE filename = '$filename' LIMIT 1;" || true)"
  if [[ "$exists" == "1" ]]; then
    echo "- SKIP  $filename (already applied)"
    skipped=$((skipped + 1))
    continue
  fi

  echo "- APPLY $filename"
  if psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$migration_file" >/dev/null; then
    psql "$DB_URL" -v ON_ERROR_STOP=1 -c "INSERT INTO public.schema_migrations (filename) VALUES ('$filename');" >/dev/null
    applied=$((applied + 1))
  else
    echo "  FAILED $filename" >&2
    failed=$((failed + 1))
    break
  fi
done < <(find "$MIGRATIONS_DIR" -maxdepth 1 -type f -name "*.sql" | sort)

# Apply test_only migrations when targeting the test env file (.env.test).
# These include e.g. the truncate_test_tables() RPC used by DatabaseAdapter.cleanup().
# They are intentionally NOT tracked in schema_migrations (idempotent, test-only).
if [[ "$ENV_FILE" == ".env.test" && -d "${MIGRATIONS_DIR}/test_only" ]]; then
  echo
  echo "Applying test_only migrations (not tracked)..."
  test_applied=0
  test_failed=0
  while IFS= read -r migration_file; do
    filename="$(basename "$migration_file")"
    echo "- APPLY (test_only) $filename"
    if psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$migration_file" >/dev/null; then
      test_applied=$((test_applied + 1))
    else
      echo "  FAILED $filename" >&2
      test_failed=$((test_failed + 1))
    fi
  done < <(find "${MIGRATIONS_DIR}/test_only" -maxdepth 1 -type f -name "*.sql" | sort)
  echo "Test-only migration summary: applied=${test_applied} failed=${test_failed}"
  if [[ $test_failed -gt 0 ]]; then
    exit 1
  fi
fi

echo
echo "Migration summary: applied=$applied skipped=$skipped failed=$failed"

if [[ $failed -gt 0 ]]; then
  exit 1
fi

echo "Done."
