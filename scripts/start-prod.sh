#!/bin/bash
# Start backend production server for a11yhood
# This script starts the backend API server on port 8000 in production mode
# Uses production Supabase database with real OAuth
# 
# Usage:
#   ./start-prod.sh        # Normal start
#   ./start-prod.sh --help # Show help
#   ./start-prod.sh --no-build # Skip image build

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Timing helper
SECONDS=0
ts() {
  echo "${SECONDS}s"
}

# Parse arguments
HELP=false
NO_BUILD=false
HTTPS_PORT=8001
HTTPS_CERTFILE=""
HTTPS_KEYFILE=""

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

# Always enable HTTPS if cert/key are provided or if local certs exist
HTTPS_ENABLED=false
if [ -z "$HTTPS_CERTFILE" ] && [ -z "$HTTPS_KEYFILE" ]; then
  # Check if local certs exist (for local development)
  if [ -f "certs/localhost.pem" ] && [ -f "certs/localhost-key.pem" ]; then
    HTTPS_ENABLED=true
    HTTPS_CERTFILE="certs/localhost.pem"
    HTTPS_KEYFILE="certs/localhost-key.pem"
  fi
elif [ -n "$HTTPS_CERTFILE" ] && [ -n "$HTTPS_KEYFILE" ]; then
  HTTPS_ENABLED=true
fi

if [ "$HELP" = true ]; then
  echo "Usage: ./start-prod.sh [OPTIONS]"
  echo ""
  echo "Starts backend production server using Docker (production Supabase database)"
  echo ""
  echo "Prerequisites:"
  echo "  - Docker running (colima start)"
  echo "  - .env configured with production Supabase credentials"
  echo "  - Production Supabase project set up with schema applied"
  echo ""
  echo "Behavior:"
  echo "  - Default: Builds Docker image locally"
  echo "  - With --no-build: Downloads image from registry (for server deployment)"
  echo "  - HTTPS: Enabled automatically if certs are available"
  echo ""
  echo "Options:"
  echo "  --help          Show this help message"
  echo "  --no-build      Skip local build, pull from registry (for server deployment)"
  echo "  --cert PATH     TLS certificate file (uses local certs by default)"
  echo "  --key PATH      TLS private key file (paired with --cert)"
  echo "  --https-port N  Host port to expose HTTPS (default: 8001)"
  echo ""
  echo "Examples:"
  echo "  ./start-prod.sh              # Build locally and run with HTTPS (if local certs exist)"
  echo "  ./start-prod.sh --no-build   # Pull from registry and run as HTTPS (for server)"
  echo "  ./start-prod.sh --cert /path/to/cert.pem --key /path/to/key.pem"
  echo ""
  echo "See documentation/DEPLOYMENT_PLAN.md for detailed setup instructions"
  exit 0
fi

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
  echo -e "${RED}✗ Docker is not running${NC}"
  echo "  Please start Docker (or Colima) first:"
  echo "    colima start"
  exit 1
fi

echo -e "${BLUE}🚀 Starting a11yhood backend PRODUCTION server (Docker)...${NC} (t=0s)"
echo ""

# Validate production environment  
if [ ! -f .env ]; then
  echo -e "${RED}✗ .env file not found${NC}"
  echo "  Production requires a .env file with Supabase credentials"
  echo "  See documentation/DEPLOYMENT_PLAN.md for setup instructions"
  exit 1
fi

# Validate Supabase environment variables
echo -e "${YELLOW}🔧 Validating production configuration...${NC} (t=$(ts))"

# Quick check without sourcing (Docker will source it)
if ! grep -q "SUPABASE_URL=" .env || ! grep -q "SUPABASE_KEY=" .env; then
  echo -e "${RED}✗ Missing required environment variables in .env${NC}"
  echo "  SUPABASE_URL and SUPABASE_KEY must be set"
  echo "  See documentation/DEPLOYMENT_PLAN.md for setup instructions"
  exit 1
fi

SUPABASE_URL=$(grep "^SUPABASE_URL=" .env | cut -d '=' -f2- | tr -d '"')

if [[ "$SUPABASE_URL" == *"localhost"* ]]; then
  echo -e "${RED}✗ SUPABASE_URL points to localhost${NC}"
  echo "  Production must use a real Supabase project URL"
  echo "  Format: https://your-project.supabase.co"
  exit 1
fi

echo -e "${GREEN}✓ Environment validated${NC}"
echo "   Supabase URL: $SUPABASE_URL"
echo ""

# If HTTPS is requested, validate certificate inputs
if [ "$HTTPS_ENABLED" = true ]; then
  if [ -z "$HTTPS_CERTFILE" ] || [ -z "$HTTPS_KEYFILE" ]; then
    echo -e "${RED}✗ HTTPS enabled but --cert/--key not provided${NC}"
    echo "  Provide paths to your TLS certificate and key using --cert and --key"
    exit 1
  fi

  if [ ! -f "$HTTPS_CERTFILE" ]; then
    echo -e "${RED}✗ TLS certificate not found:${NC} $HTTPS_CERTFILE"
    exit 1
  fi

  if [ ! -f "$HTTPS_KEYFILE" ]; then
    echo -e "${RED}✗ TLS key not found:${NC} $HTTPS_KEYFILE"
    exit 1
  fi
fi

echo -e "${YELLOW}⚠️  PRODUCTION MODE${NC}"
echo "   Using Supabase database"
echo "   OAuth enabled (real authentication)"
echo "   DO NOT seed or reset production database"
echo ""

if [ "$NO_BUILD" = false ]; then
  echo -e "${YELLOW}🔨 Building production Docker image...${NC} (t=$(ts))"
  if docker build -t a11yhood-backend:prod . 2>/tmp/build.out; then
    echo -e "${GREEN}✓ Image built${NC}"
  else
    echo -e "${RED}✗ Build failed${NC}"
    echo ""
    echo "  Build logs:"
    tail -n 30 /tmp/build.out 2>/dev/null || true
    exit 1
  fi
  echo ""
else
  echo -e "${YELLOW}📦 Pulling latest image from registry (--no-build)...${NC} (t=$(ts))"
  if docker pull ghcr.io/a11yhood/a11yhood-backend:latest 2>/tmp/pull.out; then
    echo -e "${GREEN}✓ Image pulled${NC}"
    docker tag ghcr.io/a11yhood/a11yhood-backend:latest a11yhood-backend:prod
    echo ""
  else
    echo -e "${RED}✗ Pull failed${NC}"
    echo ""
    echo "  Pull logs:"
    tail -n 30 /tmp/pull.out 2>/dev/null || true
    exit 1
  fi
fi

# Check if container is already running and stop it
echo -e "${YELLOW}🔧 Checking for existing containers...${NC} (t=$(ts))"
if docker ps -a --format "{{.Names}}" | grep -qx "a11yhood-backend-prod"; then
  echo "  Stopping existing container..."
  docker stop a11yhood-backend-prod >/dev/null 2>&1
  docker rm a11yhood-backend-prod >/dev/null 2>&1
  sleep 1
fi
if docker ps --format "{{.Names}}" | grep -qx "a11yhood-backend-dev"; then
  echo "  Development container detected and left running (a11yhood-backend-dev)."
fi
echo -e "${GREEN}✓ Ready to start${NC}"
echo ""

# Start production container
echo -e "${GREEN}🚀 Starting production container...${NC} (t=$(ts))"
HOST_PORT=8001
PROTO=http
CURL_FLAGS="-s"
HEALTH_CMD="curl -f http://localhost:8000/health || exit 1"
MOUNT_CERTS=()

if [ "$HTTPS_ENABLED" = true ]; then
  HOST_PORT=$HTTPS_PORT
  PROTO=https
  CURL_FLAGS="-ks"
  HEALTH_CMD="curl -kf https://localhost:8000/health || exit 1"
  MOUNT_CERTS=(
    -v "$(cd "$(dirname "$HTTPS_CERTFILE")" && pwd)/$(basename "$HTTPS_CERTFILE")":/certs/server.crt:ro
    -v "$(cd "$(dirname "$HTTPS_KEYFILE")" && pwd)/$(basename "$HTTPS_KEYFILE")":/certs/server.key:ro
  )
fi

echo "   Server will be available at: ${PROTO}://localhost:${HOST_PORT}"
echo "   API documentation at: ${PROTO}://localhost:${HOST_PORT}/docs"
echo ""

if [ "$HTTPS_ENABLED" = true ]; then
  docker run \
    -d \
    --name a11yhood-backend-prod \
    --env-file .env \
    -p ${HOST_PORT}:8000 \
    --restart unless-stopped \
    --health-cmd="$HEALTH_CMD" \
    --health-interval=30s \
    --health-timeout=3s \
    --health-retries=3 \
    --health-start-period=5s \
    "${MOUNT_CERTS[@]}" \
    a11yhood-backend:prod \
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --ssl-certfile /certs/server.crt --ssl-keyfile /certs/server.key
else
  docker run \
    -d \
    --name a11yhood-backend-prod \
    --env-file .env \
    -p ${HOST_PORT}:8000 \
    --restart unless-stopped \
    --health-cmd="$HEALTH_CMD" \
    --health-interval=30s \
    --health-timeout=3s \
    --health-retries=3 \
    --health-start-period=5s \
    a11yhood-backend:prod
fi

if [ $? -ne 0 ]; then
  echo -e "${RED}✗ Failed to start production container${NC}"
  exit 1
fi

# Wait for server to be ready
echo -e "${YELLOW}⏳ Waiting for server to start...${NC}"
PROBE_URL="${PROTO}://localhost:${HOST_PORT}/health"
for i in {1..60}; do
  if curl ${CURL_FLAGS} "$PROBE_URL" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is ready!${NC} (t=$(ts))"
    break
  fi
  
  # Check if container is still running
  if ! docker ps --filter "name=a11yhood-backend-prod" --format "{{.Names}}" | grep -q "a11yhood-backend-prod"; then
    echo -e "${RED}✗ Container is not running${NC}"
    echo "  Check logs with: docker logs a11yhood-backend-prod"
    exit 1
  fi
  
  sleep 1
  
  # Show progress
  if [ $i -eq 15 ]; then
    echo "  Still waiting..."
  fi
  if [ $i -eq 30 ]; then
    echo "  Taking longer than usual..."
  fi
  if [ $i -eq 45 ]; then
    echo "  Almost there..."
  fi
done

# Final check
if ! curl ${CURL_FLAGS} "$PROBE_URL" >/dev/null 2>&1; then
  echo -e "${RED}✗ Server failed to start within 60 seconds${NC}"
  echo "  Check logs with: docker logs a11yhood-backend-prod"
  docker logs --tail=50 a11yhood-backend-prod
  exit 1
fi

echo ""
echo -e "${GREEN}✅ PRODUCTION server is running!${NC} (t=$(ts))"
echo ""
echo -e "${BLUE}📡 Backend API:${NC}"
echo "   ${PROTO}://localhost:${HOST_PORT}"
echo ""
echo -e "${BLUE}📚 API Documentation:${NC}"
echo "   ${PROTO}://localhost:${HOST_PORT}/docs"
echo ""
echo -e "${BLUE}💡 To monitor logs:${NC}"
echo "   docker logs -f a11yhood-backend-prod"
echo ""
echo -e "${BLUE}🛑 To stop the server:${NC}"
echo "   ./stop-prod.sh"
echo ""
echo -e "${YELLOW}⚠️  Remember:${NC}"
echo "   - This is PRODUCTION mode with real authentication"
echo "   - Never reset or seed the production database"
echo "   - Monitor logs with: docker logs -f a11yhood-backend-prod"
echo ""
