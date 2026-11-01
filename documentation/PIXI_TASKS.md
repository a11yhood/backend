# Pixi Tasks Reference

All a11yhood development workflows use [pixi](https://pixi.sh/) tasks. This replaces individual shell scripts with a unified, discoverable interface.

## Quick Reference

### Development Environment

```bash
pixi run dev              # Run the backend locally on https://localhost:8443 (test Supabase, auto-reload)
```

### Database Management

```bash
pixi run reset                 # Restore test DB from checked-in snapshot
pixi run apply-migrations      # Apply SQL migrations to test DB (.env.test)
pixi run apply-migrations-prod # Apply migrations to production DB (.env)
pixi run seed                  # Run seed scripts
pixi run seed-list             # List available seed scripts
```

### Testing

```bash
pixi run test            # Run unit, functional, then integration tests
pixi run test-unit       # Run unit-only tests
pixi run test-functional # Run functional smoke tests
pixi run test-integration # Run integration tests (non-unit, non-functional)
pixi run test-fresh      # Reset test DB snapshot, then run the full suite
```

### Direct Server (4 workers)

```bash
pixi run serve           # Start uvicorn directly on port 8000 (requires pixi env)
```

## Detailed Task Descriptions

### Development Environment

#### `pixi run dev`
- **Purpose**: Run the backend locally with uvicorn
- **Environment**: `.env.test` (Supabase test project)
- **Address**: `https://localhost:8443` (the frontend dev server expects this)
- **Requirements**: `certs/localhost.pem` and `certs/localhost-key.pem` (mkcert-style local certificates)
- **Use when**: Developing against the Supabase test project
- **What it does**: Runs `uvicorn main:app --reload` over HTTPS; code changes reload automatically
- **Tip**: Run `pixi run reset` and/or `pixi run seed` first if you want a clean, seeded test database

### Database Management
#### `pixi run reset`
- **Purpose**: Reset test Supabase database to known-good snapshot
- **Environment**: `.env.test`
- **Use when**:
-  - Tests fail due to polluted state
-  - You need deterministic seeded baseline data
- **Notes**:
-  - Requires `SUPABASE_DB_URL` (or `DATABASE_URL`) in `.env.test`
-  - Uses `supabase/seed-test.sql`
#### `pixi run apply-migrations`
- **Purpose**: Apply SQL migrations to test Supabase database
- **Environment**: `.env.test`
- **Use when**: 
  - Setting up a fresh test Supabase project
  - Ensuring latest schema is applied
  - Running migrations before seeding
- **Notes**: 
  - Requires `psql` on your PATH
  - DB URL lookup order is env file first (`SUPABASE_DB_URL`, `DATABASE_URL`, `TEST_DATABASE_URL`), then shell-variable fallback
  - Tracks applied migrations in `public.schema_migrations` table
  - Skips already-applied migrations automatically

#### `pixi run apply-migrations-prod`
- **Purpose**: Apply SQL migrations to production Supabase database
- **Environment**: `.env`
- **Use when**: Setting up or updating production Supabase schema
- **⚠️ Warning**: Directly modifies production database—ensure backups exist!
- **Notes**: Same as `apply-migrations` but reads credentials from `.env` first, with shell-variable fallback

#### `pixi run seed`
- **Purpose**: Run development seed scripts
- **Behavior**: Runs `seed_scripts/run_seeds.py` with the local Python venv (`.venv`)
- **Use when**:
  - Populating test data after fresh schema
  - Re-seeding specific data types
  - Running custom seed subsets via options
- **Examples**:
  ```bash
  pixi run seed                                    # Run all seeds
  pixi run seed -- --include supported_sources # Run only specific seeds
  pixi run seed -- --exclude test_product      # Skip specific seeds
  ```

#### `pixi run seed-list`
- **Purpose**: List available seed scripts
- **Output**: Shows all available seed names and descriptions
- **Use when**: You want to see what can be seeded or which seeds to include/exclude

### Testing

#### `pixi run test`
- **Purpose**: Run unit tests first, then functional tests, then integration tests
- **Environment**: `.env.test` (Supabase test project)
- **Database**:
  - Unit phase avoids DB-backed fixtures entirely
  - Non-unit phase uses per-test `clean_database` resets for DB-backed fixtures
- **Use when**:
  - Validating code changes
  - Running CI/CD locally before pushing
  - Development workflow
- **Notes**: 
  - Composes `pixi run test-unit`, then `pixi run test-functional`, then `pixi run test-integration`
  - Functional and integration tests still require `SUPABASE_URL` and `SUPABASE_KEY` in `.env.test`
  - CI/CD should prefer this command for full validation

#### `pixi run test-functional`
- **Purpose**: Run the functional smoke tests that validate the app wiring end to end
- **Environment**: `.env.test`
- **Use when**:
  - You want the small end-to-end sanity set
  - Verifying app startup, auth fixture wiring, and timestamp serialization

#### `pixi run test-unit`
- **Purpose**: Run only tests marked `unit`
- **Environment**: `.env.test`
- **Database**: No DB reset path is needed for unit-only tests
- **Use when**:
  - Fast local feedback
  - Verifying offline-safe/unit-only changes
  - Running in restricted CI/firewalled environments

#### `pixi run test-integration`
- **Purpose**: Run all tests not marked `unit` or `functional`
- **Environment**: `.env.test`
- **Database**: DB-backed fixtures reset and reseed per test via `clean_database`
- **Use when**:
  - Validating DB-backed API behavior
  - Exercising seeded fixtures and authenticated flows
  - Running the slower integration half of the suite

#### `pixi run test-fresh`
- **Purpose**: Restore the test DB snapshot, then run unit, functional, and integration tests
- **Environment**: `.env.test`
- **Use when**:
-  - You need a clean test baseline before a full run
-  - Tracking flaky failures caused by leftover DB state
### Direct Server

#### `pixi run serve`
- **Purpose**: Run the FastAPI uvicorn server directly with 4 workers
- **Environment**: `.env.test`
- **Host**: `127.0.0.1`
- **Port**: 8000
- **Workers**: 4
- **Use when**:
  - Debugging with local IDE breakpoints
  - Rapid iteration on code changes
- **Requirements**:
  - Pixi environment activated: `pixi shell`
  - Supabase test project running/accessible
- **Notes**: 
  - Not for production deployment (production runs on Vercel)
  - No auto-reload with multiple workers; use `pixi run dev` for that

## Environment Variables

### `.env.test` (Development/Testing)
Used by: `dev`, `test`, `serve`, `seed`, `apply-migrations`

Contains:
- Supabase test project credentials
- Test OAuth credentials (GitHub, Ravelry, etc.)
- Test mode flags

### `.env` (Production)
Used by: `apply-migrations-prod`

Contains:
- Production Supabase credentials  
- Production OAuth credentials
- Production mode flags

Create from template: `cp .env.test.example .env` (then update values)

## Troubleshooting

### Task doesn't exist
```bash
# List all available tasks
pixi task list
```

### Port already in use
```bash
# Find and kill the process on the port
sudo lsof -i :8443
kill -9 <PID>
```

To use a different port, run uvicorn directly:
```bash
ENV_FILE=.env.test python -m uvicorn main:app --port 8444 --reload \
  --ssl-keyfile=certs/localhost-key.pem --ssl-certfile=certs/localhost.pem
```

## Configuration Details

### Shell Scripts Used By Pixi

Pixi tasks wrap these helper shell scripts (still in `scripts/`):
- `apply-migrations.sh` — PostgreSQL migration runner with tracking
- `reset-test-db.sh` — Restores the test database from the checked-in snapshot
- `seed.sh` — Seed coordinator (runs `seed_scripts/run_seeds.py`)

These are implementation details; use `pixi run <task>` instead of calling `./scripts/<script>` directly.

**Removed scripts** (replaced by pixi tasks):
- ~~`run-tests.sh`~~ → Use `pixi run test`
- ~~`start-dev.sh`, `start-prod.sh`, `stop-dev.sh`, `stop-prod.sh`, `test-prod-image.sh`~~ → Docker was removed; use `pixi run dev` (production runs on Vercel)

## Adding New Tasks

To add a new pixi task:

1. Edit `pixi.toml`
2. Add task under `[tasks.<name>]`:
   ```toml
   [tasks.my-task]
   description = "What this task does"
   cmd = "command to run"
   
   [tasks.my-task.env]
   MY_VAR = "value"
   ```

3. Run: `pixi run my-task`

See [pixi.toml](../pixi.toml) for examples.
