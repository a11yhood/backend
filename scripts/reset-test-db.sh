#!/usr/bin/env bash
set -euo pipefail

# Reset Supabase-backed test database.
#
# Preferred mode (if snapshot exists):
#   - Restores supabase/seed-test.sql via psql
#
# Fallback mode:
#   - Runs DatabaseAdapter.cleanup() against .env.test target
#   - Re-seeds via seed_scripts/seed_all.py
#
# Usage:
#   ./scripts/reset-test-db.sh
#   ./scripts/reset-test-db.sh --env-file .env.test

ENV_FILE=".env.test"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_FILE="${ROOT_DIR}/supabase/seed-test.sql"

print_help() {
  cat <<'EOF'
Reset test database.

Usage:
  ./scripts/reset-test-db.sh [--env-file PATH] [--help]

Options:
  --env-file PATH   Environment file (default: .env.test)
  --help            Show this help message

Behavior:
  1) If supabase/seed-test.sql exists and psql is available, restore snapshot.
  2) Otherwise, run cleanup + seed fallback using Python scripts.
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

if [[ "$ENV_FILE" != ".env.test" ]]; then
  echo "Error: reset can only run with .env.test." >&2
  echo "Refusing to run with ENV_FILE=${ENV_FILE}." >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/${ENV_FILE}" ]]; then
  echo "Error: env file not found: ${ENV_FILE}" >&2
  exit 1
fi

read_env_var() {
  local file="$1"
  local key="$2"

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

# IMPORTANT: read only from env file (ignore shell overrides).
TARGET_SUPABASE_URL="$(read_env_var "${ROOT_DIR}/${ENV_FILE}" "SUPABASE_URL")"
TARGET_SUPABASE_KEY="$(read_env_var "${ROOT_DIR}/${ENV_FILE}" "SUPABASE_KEY")"
DB_URL="$(read_env_var "${ROOT_DIR}/${ENV_FILE}" "SUPABASE_DB_URL")"
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(read_env_var "${ROOT_DIR}/${ENV_FILE}" "DATABASE_URL")"
fi
if [[ -z "$DB_URL" ]]; then
  DB_URL="$(read_env_var "${ROOT_DIR}/${ENV_FILE}" "TEST_DATABASE_URL")"
fi

PROD_SUPABASE_URL="$(read_env_var "${ROOT_DIR}/.env" "SUPABASE_URL")"

extract_ref() {
  local value="$1"
  if [[ "$value" =~ ^https://([^.]+)\.supabase\.co ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return
  fi
  if [[ "$value" =~ @db\.([^.]+)\.supabase\.co ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return
  fi
  if [[ "$value" =~ ^postgresql://[^@]+@([^.]+)\.([^.]+)\.pooler\.supabase\.com ]]; then
    printf '%s' "${BASH_REMATCH[2]}"
    return
  fi
  printf ''
}

TARGET_REF="$(extract_ref "$TARGET_SUPABASE_URL")"
PROD_REF="$(extract_ref "$PROD_SUPABASE_URL")"

if [[ -n "$TARGET_REF" && -n "$PROD_REF" && "$TARGET_REF" == "$PROD_REF" && "${ALLOW_RESET_ON_PROD:-}" != "1" ]]; then
  echo "Error: reset target appears to match production project ref ($TARGET_REF)." >&2
  echo "Refusing to run destructive reset using ${ENV_FILE}." >&2
  echo "If this is intentional, rerun with ALLOW_RESET_ON_PROD=1." >&2
  exit 1
fi

cd "$ROOT_DIR"

if [[ -f "$SNAPSHOT_FILE" ]] && command -v psql >/dev/null 2>&1; then
  if [[ -z "$DB_URL" ]]; then
    echo "Error: snapshot restore requires SUPABASE_DB_URL/DATABASE_URL/TEST_DATABASE_URL" >&2
    exit 1
  fi

  echo "Restoring test snapshot: ${SNAPSHOT_FILE}"
  psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$SNAPSHOT_FILE" >/dev/null
  echo "Reset complete via snapshot restore."
  exit 0
fi

echo "Snapshot not available; using cleanup + seed fallback."
if ! command -v python >/dev/null 2>&1; then
  echo "Error: python is required for fallback reset mode." >&2
  exit 1
fi

echo "Applying migrations before cleanup..."
if ! env \
  -u SUPABASE_URL \
  -u SUPABASE_KEY \
  -u SUPABASE_DB_URL \
  -u DATABASE_URL \
  -u TEST_DATABASE_URL \
  SUPABASE_DB_URL="$DB_URL" \
  "${ROOT_DIR}/scripts/apply-migrations.sh" --env-file "$ENV_FILE" >/dev/null 2>&1; then
  echo "Warning: could not apply migrations via psql (check SUPABASE_DB_URL/DATABASE_URL for direct Postgres connection)."
  echo "Continuing with API cleanup + seed fallback."
fi

env \
  -u SUPABASE_URL \
  -u SUPABASE_KEY \
  -u SUPABASE_DB_URL \
  -u DATABASE_URL \
  -u TEST_DATABASE_URL \
  ENV_FILE="$ENV_FILE" \
  SUPABASE_URL="$TARGET_SUPABASE_URL" \
  SUPABASE_KEY="$TARGET_SUPABASE_KEY" \
  SUPABASE_DB_URL="$DB_URL" \
  python - <<'PY'
from config import get_settings
from database_adapter import DatabaseAdapter

settings = get_settings()
db = DatabaseAdapter(settings)
db.cleanup()
print("Cleanup complete.")
PY

env \
  -u SUPABASE_URL \
  -u SUPABASE_KEY \
  -u SUPABASE_DB_URL \
  -u DATABASE_URL \
  -u TEST_DATABASE_URL \
  ENV_FILE="$ENV_FILE" \
  SUPABASE_URL="$TARGET_SUPABASE_URL" \
  SUPABASE_KEY="$TARGET_SUPABASE_KEY" \
  SUPABASE_DB_URL="$DB_URL" \
  python seed_scripts/seed_all.py >/dev/null

echo "Reset complete via cleanup + seed."
