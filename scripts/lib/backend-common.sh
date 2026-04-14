#!/bin/bash
# Shared helper functions for a11yhood backend scripts
# Source this file at the top of start-dev.sh, start-prod.sh, etc.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/backend-common.sh"
#   
#   setup_colors
#   check_docker_running
#   cleanup_container "container-name"
#   wait_for_health_check "http://localhost:8000/health" 30 "http"

set -euo pipefail

# ============================================================================
# Colors for terminal output
# ============================================================================

setup_colors() {
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  NC='\033[0m' # No Color
  export RED GREEN YELLOW BLUE NC
}

# ============================================================================
# Logging functions
# ============================================================================

log_info() {
  echo -e "${BLUE}ℹ️ $1${NC}"
}

log_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

log_warn() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
  echo -e "${RED}✗ $1${NC}"
}

log_step() {
  echo -e "${YELLOW}🔧 $1${NC} (t=$(ts))"
}

log_action() {
  echo -e "${GREEN}🚀 $1${NC} (t=$(ts))"
}

log_wait() {
  echo -e "${YELLOW}⏳ $1${NC}"
}

# ============================================================================
# Timing helpers
# ============================================================================

# Initialize timing (call at start of script)
init_timing() {
  SECONDS=0
}

# Get elapsed seconds since last init_timing call
ts() {
  echo "${SECONDS}s"
}

# ============================================================================
# Docker validation
# ============================================================================

check_docker_running() {
  if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running"
    echo "  Please start Docker (or Colima) first:"
    echo "    colima start"
    return 1
  fi
  return 0
}

# ============================================================================
# Container management
# ============================================================================

# Stop and remove a container if it exists
cleanup_container() {
  local container_name="$1"
  
  if docker ps -a --format "{{.Names}}" | grep -qx "$container_name"; then
    docker stop "$container_name" >/dev/null 2>&1 || true
    docker rm "$container_name" >/dev/null 2>&1 || true
    sleep 1
    return 0
  fi
  return 1
}

# Check if a container is running
is_container_running() {
  local container_name="$1"
  docker ps --filter "name=$container_name" --format "{{.Names}}" | grep -qx "$container_name"
}

# ============================================================================
# Health checks
# ============================================================================

# Wait for a service to become healthy via HTTP health check
# Args: url, timeout_seconds, protocol (http/https)
wait_for_health_check() {
  local url="$1"
  local timeout="${2:-30}"
  local proto="${3:-http}"
  local curl_flags="-s"
  
  if [ "$proto" = "https" ]; then
    curl_flags="-ks"
  fi
  
  log_wait "Waiting for server to start..."
  
  for i in $(seq 1 "$timeout"); do
    if curl $curl_flags "$url" >/dev/null 2>&1; then
      log_success "Backend is ready! (t=$(ts))"
      return 0
    fi
    
    sleep 1
    
    # Show progress messages at intervals
    if [ $i -eq 10 ]; then
      echo "  Still waiting..."
    fi
    if [ $i -eq 20 ]; then
      echo "  Taking longer than usual..."
    fi
    if [ $i -eq 30 ]; then
      echo "  Almost there..."
    fi
  done
  
  # Timeout reached
  log_error "Server failed to start within $timeout seconds"
  return 1
}

# ============================================================================
# Environment validation
# ============================================================================

validate_env_file() {
  local env_file="$1"
  
  if [ ! -f "$env_file" ]; then
    log_error "Environment file not found: $env_file"
    return 1
  fi
  
  return 0
}

# Extract a variable from an env file
# Args: filepath, variable_name
# Returns: the value (unquoted)
read_env_var() {
  local file="$1"
  local key="$2"
  
  if [ ! -f "$file" ]; then
    return 1
  fi
  
  # Extract first non-comment assignment and trim surrounding whitespace/quotes
  local line
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | head -n 1 || true)"
  if [ -z "$line" ]; then
    return 1
  fi
  
  local value
  value="${line#*=}"
  value="$(printf '%s' "$value" | sed -E "s/^[[:space:]]+//; s/[[:space:]]+$//; s/^\"(.*)\"$/\1/; s/^'(.*)'$/\1/")"
  printf '%s' "$value"
}

# ============================================================================
# Docker build & image management
# ============================================================================

# Build Docker image with error handling
# Args: tag, dockerfile_context
build_docker_image() {
  local tag="$1"
  local context="${2:-.}"
  
  log_step "Building Docker image ($tag)..."
  if docker build -t "$tag" "$context" 2>/tmp/build.out; then
    log_success "Image built"
    return 0
  else
    log_error "Build failed"
    echo ""
    echo "  Build logs:"
    tail -n 30 /tmp/build.out 2>/dev/null || true
    return 1
  fi
}

# Pull Docker image from registry with error handling
# Args: image_name, local_tag (optional)
pull_docker_image() {
  local image="$1"
  local local_tag="${2:-${image##*/}}"
  
  log_step "Pulling image from registry ($image)..."
  if docker pull "$image" 2>/tmp/pull.out; then
    log_success "Image pulled"
    docker tag "$image" "$local_tag"
    return 0
  else
    log_error "Pull failed"
    echo ""
    echo "  Pull logs:"
    tail -n 30 /tmp/pull.out 2>/dev/null || true
    return 1
  fi
}

# ============================================================================
# Container startup
# ============================================================================

# Run docker container for development (with volume mount for hot reload)
# Args: container_name, image_tag, port, env_file
run_dev_container() {
  local container_name="$1"
  local image_tag="$2"
  local port="$3"
  local env_file="$4"
  
  log_action "Starting backend container..."
  echo "   Server will be available at: http://localhost:${port}"
  echo "   API documentation at: http://localhost:${port}/docs"
  echo "   Code changes will auto-reload"
  echo ""
  
  docker run \
    -d \
    --name "$container_name" \
    --env-file "$env_file" \
    -e ENV_FILE="$env_file" \
    -p "${port}:8000" \
    -v "$(pwd):/app" \
    --restart unless-stopped \
    --health-cmd="python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/health\", timeout=2)'" \
    --health-interval=30s \
    --health-timeout=3s \
    --health-retries=3 \
    --health-start-period=5s \
    "$image_tag" \
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
}

# Run docker container for production (no volume mount, multiple workers)
# Args: container_name, image_tag, port, env_file, [use_https], [cert_file], [key_file]
run_prod_container() {
  local container_name="$1"
  local image_tag="$2"
  local port="$3"
  local env_file="$4"
  local use_https="${5:-false}"
  local cert_file="${6:-}"
  local key_file="${7:-}"
  
  local uvicorn_args="uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4"
  local mount_args=()
  local scheme="http"
  if [ "$use_https" = "true" ]; then
    scheme="https"
  fi

  local health_cmd
  if [ "$use_https" = "true" ]; then
    health_cmd="python -c 'import urllib.request, ssl; ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE; urllib.request.urlopen(\"https://localhost:8000/health\", context=ctx, timeout=2)'"
  else
    health_cmd="python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/health\", timeout=2)'"
  fi
  
  log_action "Starting production container..."
  echo "   Server will be available at: ${scheme}://localhost:${port}"
  echo "   API documentation at: ${scheme}://localhost:${port}/docs"
  echo ""
  
  if [ "$use_https" = "true" ] && [ -n "$cert_file" ] && [ -n "$key_file" ]; then
    uvicorn_args="$uvicorn_args --ssl-certfile /certs/server.crt --ssl-keyfile /certs/server.key"
    mount_args=(
      -v "$(cd "$(dirname "$cert_file")" && pwd)/$(basename "$cert_file")":/certs/server.crt:ro
      -v "$(cd "$(dirname "$key_file")" && pwd)/$(basename "$key_file")":/certs/server.key:ro
    )
  fi
  
  docker run \
    -d \
    --name "$container_name" \
    --env-file "$env_file" \
    -p "${port}:8000" \
    --restart unless-stopped \
    --health-cmd="$health_cmd" \
    --health-interval=30s \
    --health-timeout=3s \
    --health-retries=3 \
    --health-start-period=5s \
    "${mount_args[@]}" \
    "$image_tag" \
    $uvicorn_args
}
