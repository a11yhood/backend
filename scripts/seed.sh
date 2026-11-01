#!/bin/bash
# Convenient helper to run seed scripts
#
# Usage:
#   ./scripts/seed.sh              # Run seeds
#   ./scripts/seed.sh --list       # List available seeds
#   ./scripts/seed.sh --help       # Show help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

# Show help
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat << 'EOF'
Seed Script Runner - a11yhood Backend

Usage:
  ./scripts/seed.sh              Run all development seeds
  ./scripts/seed.sh --list       List available seeds
  ./scripts/seed.sh --help       Show this help message
  
Advanced usage:
  # Run with options (pass through to run_seeds.py)
  ./scripts/seed.sh --include supported_sources,oauth_configs
  ./scripts/seed.sh --exclude test_product,test_collections
  
Environment:
  ENV_FILE              Override default .env.test location
                        (e.g., ENV_FILE=.env ./scripts/seed.sh)

Examples:
  # Run all seeds for development
  ./scripts/seed.sh
  
  # Run only database setup, skip test data
  ./scripts/seed.sh --exclude test_product,test_collections
  
  # See what seeds are available
  ./scripts/seed.sh --list

EOF
    exit 0
fi

if [ ! -f "$PYTHON" ]; then
  echo "Error: Python virtual environment not found at $SCRIPT_DIR/.venv"
  echo "Please set up the virtual environment first"
  exit 1
fi

echo "🌱 Running seed scripts..."
"$PYTHON" "$SCRIPT_DIR/seed_scripts/run_seeds.py" "$@"
