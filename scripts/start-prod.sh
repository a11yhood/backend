#!/bin/bash
# Start backend production server for a11yhood
# This script starts the backend API server on port 8000 in production mode
# Uses production Supabase database with real OAuth
# 
# Usage:
#   ./start-prod.sh        # Normal start
#   ./start-prod.sh --help # Show help
#   ./start-prod.sh --no-build # Skip image build

set -euo pipefail

# Source common helper functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/backend-common.sh"

# ============================================================================
# Configuration
# ============================================================================

CONTAINER_NAME="a11yhood-backend-prod"
IMAGE_TAG="a11yhood-backend:prod"
ENV_FILE=".env"
HOST_PORT=8001
HTTPS_PORT=8001
HTTPS_CERTFILE=""
HTTPS_KEYFILE=""
NO_BUILD=false
HELP=false
HTTPS_ENABLED=false

# ============================================================================
# Argument parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      HELP=true
      shift
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --https-port)
      HTTPS_PORT="$2"
      shift 2
      ;;
    --cert)
      HTTPS_CERTFILE="$2"
      shift 2
      ;;
    --key)
      HTTPS_KEYFILE="$2"
      shift 2
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
Usage: ./start-prod.sh [OPTIONS]

Start a11yhood backend production server in Docker, backed by production Supabase.

Prerequisites:
  - Docker running (colima start)
  - .env configured with production Supabase credentials
  - Production Supabase project set up with schema applied

Behavior:
  - Default: Builds Docker image locally
  - With --no-build: Downloads image from registry (for server deployment)
  - HTTPS: Enabled automatically if local certs exist

Options:
  --help          Show this help message
  --no-build      Skip local build, pull from registry (for server deployment)
  --cert PATH     TLS certificate file (uses local certs by default)
  --key PATH      TLS private key file (paired with --cert)
  --https-port N  Host port to expose HTTPS (default: 8001)

Examples:
  ./start-prod.sh              # Build locally, use HTTPS if certs available
  ./start-prod.sh --no-build   # Pull from registry, use HTTPS
  ./start-prod.sh --cert /path/to/cert.pem --key /path/to/key.pem

See documentation/DEPLOYMENT_PLAN.md for detailed setup instructions.
EOF
  exit 0
fi

# ============================================================================
# Initialization
# ============================================================================

setup_colors
init_timing

echo -e "${BLUE}🚀 Starting a11yhood backend PRODUCTION server (Docker)...${NC} (t=0s)"
echo ""

# Validate Docker
if ! check_docker_running; then
  exit 1
fi

# ============================================================================
# Production environment validation
# ============================================================================

if ! validate_env_file "$ENV_FILE"; then
  log_error "Production requires a .env file with Supabase credentials"
  echo "  See documentation/DEPLOYMENT_PLAN.md for setup instructions"
  exit 1
fi

log_step "Validating production configuration..."

# Validate required Supabase config
if ! grep -q "SUPABASE_URL=" "$ENV_FILE" || ! grep -q "SUPABASE_KEY=" "$ENV_FILE"; then
  log_error "Missing required environment variables in .env"
  echo "  SUPABASE_URL and SUPABASE_KEY must be set"
  exit 1
fi

# Read and validate Supabase URL (not localhost)
SUPABASE_URL=$(read_env_var "$ENV_FILE" "SUPABASE_URL" || true)
if [[ "$SUPABASE_URL" == *"localhost"* ]]; then
  log_error "SUPABASE_URL points to localhost"
  echo "  Production must use a real Supabase project URL"
  echo "  Format: https://your-project.supabase.co"
  exit 1
fi

log_success "Environment validated"
echo "   Supabase URL: $SUPABASE_URL"
echo ""

# Validate HTTPS certificates if enabled
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

log_warn "PRODUCTION MODE"
echo "   Using Supabase database"
echo "   OAuth enabled (real authentication)"
echo "   DO NOT seed or reset production database"
echo ""

# ============================================================================
# Build or pull Docker image
# ============================================================================

if [ "$NO_BUILD" = false ]; then
  if ! build_docker_image "$IMAGE_TAG" "."; then
    exit 1
  fi
else
  if ! pull_docker_image "ghcr.io/a11yhood/a11yhood-backend:latest" "$IMAGE_TAG"; then
    exit 1
  fi
fi
echo ""

# ============================================================================
# Container preparation
# ============================================================================

log_step "Checking for existing containers..."
if cleanup_container "$CONTAINER_NAME"; then
  echo "  Stopped existing container"
fi
if is_container_running "a11yhood-backend-dev"; then
  echo "  Development container detected and left running"
fi
log_success "Ready to start"
echo ""

# ============================================================================
# Start container
# ============================================================================

PROTO="http"
if [ "$HTTPS_ENABLED" = true ]; then
  PROTO="https"
  if ! run_prod_container "$CONTAINER_NAME" "$IMAGE_TAG" "$HOST_PORT" "$ENV_FILE" "true" "$HTTPS_CERTFILE" "$HTTPS_KEYFILE"; then
    log_error "Failed to start container"
    exit 1
  fi
else
  if ! run_prod_container "$CONTAINER_NAME" "$IMAGE_TAG" "$HOST_PORT" "$ENV_FILE" "false"; then
    log_error "Failed to start container"
    exit 1
  fi
fi

# ============================================================================
# Health check
# ============================================================================

HEALTH_URL="${PROTO}://localhost:${HOST_PORT}/health"
if [ "$PROTO" = "https" ]; then
  # HTTPS health check requires curl to ignore cert validation
  if ! wait_for_health_check "$HEALTH_URL" 60 "https"; then
    log_error "Container is not running"
    echo "  Check logs with: docker logs $CONTAINER_NAME"
    docker logs --tail=50 "$CONTAINER_NAME" 2>/dev/null || true
    exit 1
  fi
else
  if ! wait_for_health_check "$HEALTH_URL" 60 "http"; then
    log_error "Container is not running"
    echo "  Check logs with: docker logs $CONTAINER_NAME"
    docker logs --tail=50 "$CONTAINER_NAME" 2>/dev/null || true
    exit 1
  fi
fi

# ============================================================================
# Startup summary
# ============================================================================

echo ""
log_success "PRODUCTION server is running! (t=$(ts))"
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
echo "   pixi run prod-stop"
echo ""
log_warn "Remember:"
echo "   - This is PRODUCTION mode with real authentication"
echo "   - Never reset or seed the production database"
echo "   - Monitor logs with: docker logs -f $CONTAINER_NAME"
echo ""
