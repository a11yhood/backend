#!/bin/bash
# Smoke-test the production Docker image locally.
#
# Builds the same image the CI workflow produces (no volume mount, 4 workers),
# runs it against .env.test on a dedicated port, verifies the key HTTP endpoints,
# then cleans up.
#
# Usage:
#   ./scripts/test-prod-image.sh            # build fresh image + smoke test
#   ./scripts/test-prod-image.sh --no-build # skip build, re-use existing image
#
# Exit codes:
#   0 – all smoke checks passed
#   1 – build, startup, or at least one check failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/backend-common.sh"

# ============================================================================
# Configuration
# ============================================================================

CONTAINER_NAME="a11yhood-backend-smoke"
IMAGE_TAG="a11yhood-backend:prod-smoke"
HOST_PORT=8099
ENV_FILE=".env.test"
NO_BUILD=false

# ============================================================================
# Argument parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      NO_BUILD=true
      shift
      ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [--no-build]

  --no-build   Skip docker build; use the existing '$IMAGE_TAG' image.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# ============================================================================
# Helpers
# ============================================================================

setup_colors
init_timing

PASS=0
FAIL=0

smoke_check() {
  local label="$1"
  local expected_status="$2"
  local url="$3"

  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

  if [[ "$actual" == "$expected_status" ]]; then
    log_success "  $label → HTTP $actual"
    PASS=$(( PASS + 1 ))
  else
    log_error "  $label → expected HTTP $expected_status, got $actual  ($url)"
    FAIL=$(( FAIL + 1 ))
  fi
}

smoke_check_body() {
  local label="$1"
  local pattern="$2"       # substring to grep for in the response body
  local url="$3"

  local body
  body=$(curl -s "$url" 2>/dev/null || true)
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

  if echo "$body" | grep -q "$pattern"; then
    log_success "  $label → HTTP $status, body contains '$pattern'"
    PASS=$(( PASS + 1 ))
  else
    log_error "  $label → pattern '$pattern' not found in response (HTTP $status)"
    echo "     Body preview: $(echo "$body" | head -c 200)"
    FAIL=$(( FAIL + 1 ))
  fi
}

# ============================================================================
# Cleanup on exit
# ============================================================================

cleanup() {
  if docker ps -a --format "{{.Names}}" 2>/dev/null | grep -qx "$CONTAINER_NAME"; then
    log_step "Stopping smoke container..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rm   "$CONTAINER_NAME" >/dev/null 2>&1 || true
    log_success "Container removed"
  fi
}
trap cleanup EXIT

# ============================================================================
# Pre-flight
# ============================================================================

echo -e "${BLUE}🔬 Production image smoke test${NC}  (t=0s)"
echo ""

if ! check_docker_running; then
  exit 1
fi

if ! validate_env_file "$ENV_FILE"; then
  log_error "Required: $ENV_FILE with Supabase test credentials"
  exit 1
fi

# Stop any leftover smoke container from a previous run
cleanup_container "$CONTAINER_NAME" || true

# ============================================================================
# Build
# ============================================================================

if [ "$NO_BUILD" = false ]; then
  if ! build_docker_image "$IMAGE_TAG" "."; then
    exit 1
  fi
else
  if ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    log_error "Image '$IMAGE_TAG' not found locally. Run without --no-build first."
    exit 1
  fi
  log_info "Re-using existing image: $IMAGE_TAG"
fi
echo ""

# ============================================================================
# Start container (prod-mode: no volume mount, 4 workers)
# ============================================================================

log_step "Starting smoke container on port $HOST_PORT..."

docker run \
  -d \
  --name "$CONTAINER_NAME" \
  --env-file "$ENV_FILE" \
  -e ENV_FILE="$ENV_FILE" \
  -p "${HOST_PORT}:8000" \
  --health-cmd="python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/health\", timeout=2)'" \
  --health-interval=10s \
  --health-timeout=3s \
  --health-retries=5 \
  --health-start-period=5s \
  "$IMAGE_TAG" \
  uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

BASE="http://localhost:${HOST_PORT}"

# Wait for /health to respond (up to 60 s), failing fast if the container exits
log_wait "Waiting for server to start..."
STARTED=false
for i in $(seq 1 60); do
  # Fast-fail: container exited unexpectedly
  if ! docker ps --format "{{.Names}}" | grep -qx "$CONTAINER_NAME"; then
    log_error "Container exited unexpectedly after ${i}s"
    echo "  Container logs:"
    docker logs --tail=60 "$CONTAINER_NAME" 2>/dev/null || true
    exit 1
  fi

  if curl -s --connect-timeout 2 "$BASE/health" >/dev/null 2>&1; then
    log_success "Backend is ready! (t=$(ts))"
    STARTED=true
    break
  fi

  sleep 1
  [[ $i -eq 15 ]] && echo "  Still waiting..."
  [[ $i -eq 30 ]] && echo "  Taking longer than usual..."
done

if [ "$STARTED" = false ]; then
  log_error "Server failed to start within 60 seconds"
  echo "  Container logs:"
  docker logs --tail=60 "$CONTAINER_NAME" 2>/dev/null || true
  exit 1
fi
echo ""

# ============================================================================
# Smoke checks
# ============================================================================

log_info "Running smoke checks against $BASE ..."
echo ""

# Server infrastructure
smoke_check_body "GET /health → status=healthy"   '"healthy"'    "$BASE/health"
smoke_check      "GET /docs   → 200"              "200"          "$BASE/docs"
smoke_check      "GET /openapi.json → 200"        "200"          "$BASE/openapi.json"

# Core product endpoints (unauthenticated reads)
smoke_check      "GET /api/products       → 200"  "200"          "$BASE/api/products"
smoke_check      "GET /api/products/count → 200"  "200"          "$BASE/api/products/count"
smoke_check      "GET /api/products/types → 200"  "200"          "$BASE/api/products/types"
smoke_check      "GET /api/products/tags  → 200"  "200"          "$BASE/api/products/tags"

# 404 for unknown path (ensures error handler is wired)
smoke_check      "GET /no-such-path → 404"        "404"          "$BASE/no-such-path"

# ============================================================================
# Result summary
# ============================================================================

echo ""
echo "──────────────────────────────────────────"
TOTAL=$(( PASS + FAIL ))
if [ "$FAIL" -eq 0 ]; then
  log_success "All $TOTAL smoke checks passed  (t=$(ts))"
  echo ""
  exit 0
else
  log_error "$FAIL / $TOTAL checks failed  (t=$(ts))"
  echo ""
  echo "  Container logs:"
  docker logs --tail=60 "$CONTAINER_NAME" 2>/dev/null || true
  exit 1
fi
