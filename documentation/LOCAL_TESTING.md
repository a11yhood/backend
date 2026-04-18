# Local Testing Guide

This guide is pixi-first. Run commands from the repo root.

## Prerequisites

- Docker running
- pixi installed
- .env.test configured with test Supabase credentials
- SUPABASE_DB_URL in .env.test for reset tooling

### Install Pixi (macOS)

Visit https://pixi.prefix.dev for more information.

Choose one option:

```bash
# Homebrew
brew install pixi
```

```bash
# Official installer
curl -fsSL https://pixi.sh/install.sh | bash
```

Verify installation:

```bash
pixi --version
```

## Quick Start

```bash
# Start backend in dev mode (Docker, test Supabase)
pixi run dev

# Optional script version
./start-dev.sh


# Stop backend
pixi run dev-stop

# Optional Script Version
./stop-dev.sh

```

## Core URLs

| Component | URL |
|---|---|
| Backend API | http://localhost:8002 |
| API Docs | http://localhost:8002/docs |
| Health | http://localhost:8002/health |

## Test Users

The test environment is seeded with these users:

| Username | GitHub ID | Role |
|---|---|---|
| admin_user | admin-test-001 | admin |
| moderator_user | mod-test-002 | moderator |
| regular_user | user-test-003 | user |

## Database Reset And Seed

### Reset test database (authoritative snapshot)

```bash
pixi run reset
```

What this does:
- Restores from the checked-in snapshot at supabase/seed-test.sql
- Resets deterministic seeded data
- Syncs identity sequence state needed by tests

### Start dev with reset + seed

```bash
pixi run dev-reset
```

### Seed without reset

```bash
pixi run seed
```

### List seed options

```bash
pixi run seed-list
```

## Running Tests

```bash
# Full suite as two phases (uses .env.test)
pixi run test

# Unit-only fast path
pixi run test-unit

# Non-unit / DB-backed path (per-test reset via clean_database)
pixi run test-integration

# Fresh DB snapshot + full suite
pixi run test-fresh

# Single file / single test selection
pixi run pytest tests/test_collections.py -v
pixi run pytest tests/test_collections.py::TestGetCollectionDetails::test_get_collection_details_includes_product_slugs -v
```

## Scraper Testing (Simplified)

Use these two paths only:

1. UI path
- Start dev: pixi run dev
- Log in as admin_user
- Open Scraper Manager
- Run a scraper in test mode

2. API path
- Call the scraper endpoint from /docs
- Keep TEST_MODE=true in .env.test

Notes:
- In test mode, scheduled scrapers are disabled.
- Test mode uses limits to avoid large external pulls.

## Environment Sanity Check

Prefer explicit checks over shell parsing tricks:

```bash
# Confirm required test keys exist (do not print secrets)
rg -n '^(TEST_MODE|SUPABASE_URL|SUPABASE_DB_URL)=' .env.test

# Confirm backend is running in test mode
curl -s http://localhost:8002/health
```

## Troubleshooting

### Reset fails with no database URL

Add SUPABASE_DB_URL to .env.test.

### Tests fail from polluted data

```bash
pixi run reset
pixi run test -- tests/test_collections.py -v
```

### Port already in use

```bash
pixi run dev-stop
pixi run dev
```

## Command Policy

For local backend work:
- Use pixi commands first.
- Use scripts directly only when a pixi task does not exist.

See documentation/PIXI_TASKS.md for all supported tasks.
