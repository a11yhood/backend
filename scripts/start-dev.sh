#!/bin/bash
# Start backend development server for a11yhood using Docker
# This script starts the backend API server on port 8002 in a Docker container
# backed by the Supabase test project configured in .env.test.
#
# Usage:
#   ./start-dev.sh              # Normal start
#   ./start-dev.sh --reset-db   # Reset Supabase test data before optional seeding
#   ./start-dev.sh --port 8002  # Expose dev service on a custom host port
#   ./start-dev.sh --no-build   # Skip local build and pull from registry
#   ./start-dev.sh --https-port 8443 --cert certs/localhost.pem --key certs/localhost-key.pem
#   ./start-dev.sh --help       # Show help

set -euo pipefail

# Source common helper functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/backend-common.sh"

# ============================================================================
# Configuration
# ============================================================================

CONTAINER_NAME="a11yhood-backend-dev"
IMAGE_TAG="a11yhood-backend:dev"
ENV_FILE=".env.test"
HOST_PORT=8002
HTTPS_PORT=8443
HTTPS_CERTFILE=""
HTTPS_KEYFILE=""
RESET_DB=false
SEED_DB=false
NO_BUILD=false
HTTPS_ENABLED=false
HELP=false

# ============================================================================
# Argument parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
  case $1 in
    --reset-db)
      RESET_DB=true
      shift
      ;;
    --seed)
      SEED_DB=true
      shift
      ;;
    --port)
      if [[ $# -lt 2 ]]; then
        echo "Error: --port requires a value"
        exit 1
      fi
      HOST_PORT="$2"
      shift 2
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --https-port)
      if [[ $# -lt 2 ]]; then
        echo "Error: --https-port requires a value"
        exit 1
      fi
      HTTPS_PORT="$2"
      shift 2
      ;;
    --cert)
      if [[ $# -lt 2 ]]; then
        echo "Error: --cert requires a value"
        exit 1
      fi
      HTTPS_CERTFILE="$2"
      shift 2
      ;;
    --key)
      if [[ $# -lt 2 ]]; then
        echo "Error: --key requires a value"
        exit 1
      fi
      HTTPS_KEYFILE="$2"
      shift 2
      ;;
    --help)
      HELP=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      HELP=true
      shift
      ;;
  esac
done

# Detect HTTPS: explicit cert/key or local certs
if [ -n "$HTTPS_CERTFILE" ] && [ -n "$HTTPS_KEYFILE" ]; then
  HTTPS_ENABLED=true
  HOST_PORT=$HTTPS_PORT
elif [ -f "certs/localhost.pem" ] && [ -f "certs/localhost-key.pem" ]; then
  HTTPS_ENABLED=true
  HTTPS_CERTFILE="certs/localhost.pem"
  HTTPS_KEYFILE="certs/localhost-key.pem"
  HOST_PORT=$HTTPS_PORT
fi

if [ "$HELP" = true ]; then
  cat <<'EOF'
Usage: ./start-dev.sh [OPTIONS]

Start a11yhood backend development server in Docker, backed by Supabase test project.

Options:
  --reset-db   Reset Supabase test data before optional seeding
  --seed       Seed the database with test data
  --port       Host port for the Docker container (default: 8002)
  --no-build   Skip local build, pull from registry instead
  --cert PATH  TLS certificate file (enables HTTPS)
  --key PATH   TLS private key file (paired with --cert)
  --https-port Host port for HTTPS when TLS is enabled (default: 8443)
  --help       Show this help message

Examples:
  ./start-dev.sh                # Normal start
  ./start-dev.sh --reset-db     # Reset test data
  ./start-dev.sh --seed         # Start and seed
  ./start-dev.sh --port 8003    # Use custom port
  ./start-dev.sh --no-build     # Pull image from registry
  ./start-dev.sh --cert certs/localhost.pem --key certs/localhost-key.pem
  ./start-dev.sh --reset-db --seed  # Reset and seed

Environment:
  .env.test   - Development environment config (required if using this script)

See documentation/PIXI_TASKS.md for pixi commands that wrap this script.
EOF
  exit 0
fi

# ============================================================================
# Initialization
# ============================================================================

setup_colors
init_timing

echo -e "${BLUE}🚀 Starting a11yhood backend development server (Docker)...${NC} (t=0s)"
echo ""

# Validate Docker
if ! check_docker_running; then
  exit 1
fi

if ! validate_env_file "$ENV_FILE"; then
  log_error "Development requires $ENV_FILE with test Supabase credentials"
  exit 1
fi

if [ "$HTTPS_ENABLED" = true ]; then
  if [ ! -f "$HTTPS_CERTFILE" ]; then
    log_error "TLS certificate not found: $HTTPS_CERTFILE"
    exit 1
  fi
  if [ ! -f "$HTTPS_KEYFILE" ]; then
    log_error "TLS key not found: $HTTPS_KEYFILE"
    exit 1
  fi
fi

# ============================================================================
# Container preparation
# ============================================================================

prepare_container_startup "$CONTAINER_NAME" "a11yhood-backend-prod" "Production"

# ============================================================================
# Build or pull Docker image
# ============================================================================

if ! ensure_docker_image "$IMAGE_TAG" "$NO_BUILD" "ghcr.io/a11yhood/a11yhood-backend:latest"; then
  exit 1
fi
echo ""

# ============================================================================
# Start container
# ============================================================================

if [ "$HTTPS_ENABLED" = true ]; then
  if ! run_dev_container "$CONTAINER_NAME" "$IMAGE_TAG" "$HOST_PORT" "$ENV_FILE" "true" "$HTTPS_CERTFILE" "$HTTPS_KEYFILE"; then
    log_error "Failed to start container"
    exit 1
  fi
else
  if ! run_dev_container "$CONTAINER_NAME" "$IMAGE_TAG" "$HOST_PORT" "$ENV_FILE" "false"; then
    log_error "Failed to start container"
    exit 1
  fi
fi

# ============================================================================
# Health check
# ============================================================================

PROTO="http"
if [ "$HTTPS_ENABLED" = true ]; then
  PROTO="https"
fi

HEALTH_URL="${PROTO}://localhost:${HOST_PORT}/health"
if ! verify_container_health "$HEALTH_URL" 60 "$PROTO" "$CONTAINER_NAME"; then
  exit 1
fi

# ============================================================================
# Database operations (if requested)
# ============================================================================

# Reset test data if requested
if [ "$RESET_DB" = true ]; then
  echo ""
  log_step "Resetting Supabase test data..."
  if docker exec -w /app "$CONTAINER_NAME" bash -c "export ENV_FILE=.env.test && /usr/local/bin/python3 - <<'PY'
from config import get_settings
from database_adapter import DatabaseAdapter

db = DatabaseAdapter(get_settings('.env.test'))
db.cleanup()
print('Supabase test data reset complete.')
PY" >/dev/null 2>&1; then
    log_success "Supabase test data reset"
  else
    log_error "Reset failed"
    echo "  Check logs with: docker logs $CONTAINER_NAME"
    exit 1
  fi
fi

# Seed database if requested
if [ "$SEED_DB" = true ]; then
  echo ""
  log_step "Seeding database inside container..."
  if docker exec -w /app "$CONTAINER_NAME" bash -c "export ENV_FILE=.env.test && /usr/local/bin/python3 seed_scripts/seed_all.py" >/dev/null 2>&1; then
    log_success "Database seeded"
  else
    log_error "Seeding failed"
    echo "  Check logs with: docker logs $CONTAINER_NAME"
    exit 1
  fi
fi

# ============================================================================
# Startup summary
# ============================================================================

echo ""
log_success "Development environment is running! (t=$(ts))"
echo ""
log_info "Backend API:"
echo "   ${PROTO}://localhost:${HOST_PORT}"
echo ""
log_info "API Documentation:"
echo "   ${PROTO}://localhost:${HOST_PORT}/docs"
echo ""
log_info "To monitor logs:"
echo "   docker logs -f $CONTAINER_NAME"
echo ""
log_info "To stop the server:"
echo "   pixi run dev-stop"
echo ""
