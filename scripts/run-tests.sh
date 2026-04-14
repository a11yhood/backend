#!/usr/bin/env bash
set -euo pipefail

# Run backend tests for a11yhood
# Usage:
#   ./run-tests.sh                    # Run all tests
#   ./run-tests.sh -v                 # Run with verbose output
#   ./run-tests.sh -k test_name       # Run specific test
#   ./run-tests.sh --cov              # Run with coverage report
#   ./run-tests.sh --help             # Show this help message

HELP=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      HELP=true
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [ "$HELP" = true ]; then
  echo "Usage: ./run-tests.sh [OPTIONS]"
  echo ""
  echo "Run backend tests for a11yhood"
  echo ""
  echo "Options:"
  echo "  -v, --verbose    Verbose output"
  echo "  -k TEST_NAME     Run specific test by name"
  echo "  --cov            Run with coverage report"
  echo "  --help           Show this help message"
  echo ""
  echo "Examples:"
  echo "  ./run-tests.sh               # Run all tests"
  echo "  ./run-tests.sh -v            # Verbose mode"
  echo "  ./run-tests.sh -k test_user  # Run tests matching 'test_user'"
  echo "  ./run-tests.sh --cov         # Generate coverage report"
  exit 0
fi

echo "🧪 Running backend tests..."
echo ""

# Use uv if available, otherwise use python
if command -v uv >/dev/null 2>&1; then
  uv run pytest "$@"
else
  python -m pytest "$@"
fi
