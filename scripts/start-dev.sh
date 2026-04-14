#!/bin/bash
# Start backend development server for a11yhood using Docker
# This script starts the backend API server on port 8000 in a Docker container
# backed by the Supabase test project configured in .env.test.
#
# Usage:
#   ./start-dev.sh              # Normal start
#   ./start-dev.sh --reset-db   # Reset Supabase test data before optional seeding
#   ./start-dev.sh --port 8002  # Expose dev service on a custom host port
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
RESET_DB=false
SEED_DB=false
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

if [ "$HELP" = true ]; then
  cat <<'EOF'
Usage: ./start-dev.sh [OPTIONS]

Start a11yhood backend development server in Docker, backed by Supabase test project.

Options:
  --reset-db   Reset Supabase test data before optional seeding
  --seed       Seed the database with test data
  --port       Host port for the Docker container (default: 8002)
  --help       Show this help message

Examples:
  ./start-dev.sh                # Normal start
  ./start-dev.sh --reset-db     # Reset test data
  ./start-dev.sh --seed         # Start and seed
  ./start-dev.sh --port 8003    # Use custom port
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

# ============================================================================
# Container preparation
# ============================================================================

log_step "Checking for existing containers..."
if cleanup_container "$CONTAINER_NAME"; then
  echo "  Stopped existing container"
fi
if is_container_running "a11yhood-backend-prod"; then
  echo "  Production container detected and left running"
fi
log_success "Ready to start"
echo ""

# ============================================================================
# Build Docker image
# ============================================================================

if ! build_docker_image "$IMAGE_TAG" "."; then
  exit 1
fi
echo ""

# ============================================================================
# Start container
# ============================================================================

if ! run_dev_container "$CONTAINER_NAME" "$IMAGE_TAG" "$HOST_PORT" "$ENV_FILE"; then
  log_error "Failed to start container"
  exit 1
fi

# ============================================================================
# Health check
# ============================================================================

HEALTH_URL="http://localhost:${HOST_PORT}/health"
if ! wait_for_health_check "$HEALTH_URL" 30 "http"; then
  log_error "Container is not running"
  echo "  Check logs with: docker logs $CONTAINER_NAME"
  docker logs --tail=50 "$CONTAINER_NAME" 2>/dev/null || true
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
echo "   http://localhost:${HOST_PORT}"
echo ""
log_info "API Documentation:"
echo "   http://localhost:${HOST_PORT}/docs"
echo ""
log_info "To monitor logs:"
echo "   docker logs -f $CONTAINER_NAME"
echo ""
log_info "To stop the server:"
echo "   pixi run dev-stop"
echo ""
