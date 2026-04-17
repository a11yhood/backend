# Pixi Tasks Reference

All a11yhood development workflows use [pixi](https://pixi.sh/) tasks. This replaces individual shell scripts with a unified, discoverable interface.

## Quick Reference

### Development Environment

```bash
pixi run dev              # Start dev backend on port 8002 (test Supabase)
pixi run dev-seed        # Start dev + seed test data
pixi run dev-reset       # Start dev + reset & seed test data  
pixi run dev-stop        # Stop dev backend container
```

### Production Environment (Local Validation)

```bash
pixi run prod            # Start prod backend on port 8001 (production Supabase)
pixi run prod-stop       # Stop prod backend container
```

### Database Management

```bash
pixi run reset                 # Restore test DB from checked-in snapshot
pixi run apply-migrations      # Apply SQL migrations to test DB (.env.test)
pixi run apply-migrations-prod # Apply migrations to production DB (.env)
pixi run seed                  # Run seed scripts (auto-detects Docker or local)
pixi run seed-list             # List available seed scripts
```

### Testing

```bash
pixi run test            # Run unit tests, then non-unit tests
pixi run test-unit       # Run unit-only tests
pixi run test-integration # Run non-unit tests (DB-backed tests reset per test)
pixi run test-fresh      # Reset test DB snapshot, then run both paths
```

### Direct Server (No Docker)

```bash
pixi run serve           # Start uvicorn directly on port 8000 (requires pixi env)
```

## Detailed Task Descriptions

### Development Environment

#### `pixi run dev`
- **Purpose**: Start the development backend in Docker
- **Environment**: `.env.test` (Supabase test project)
- **Port**: 8002
- **Use when**: You want to develop with a fresh Supabase test database
- **What it does**: Builds Docker image, starts `backend-dev` container, runs health checks

#### `pixi run dev-seed`
- **Purpose**: Start development backend and seed test data
- **Environment**: `.env.test`
- **Port**: 8002
- **Use when**: You want test data (users, products, sources) pre-populated
- **What it does**: Runs `dev` + automatically runs all seed scripts inside the container

#### `pixi run dev-reset`
- **Purpose**: Start development backend with fresh database
- **Environment**: `.env.test`
- **Port**: 8002
- **Use when**: You want to completely reset the test database and start fresh
- **What it does**: 
  1. Resets Supabase test project schema
  2. Re-applies all migrations
  3. Seeds test data

#### `pixi run dev-stop`
- **Purpose**: Stop the development backend container
- **Cleanup**: Removes the `backend-dev` container
- **Use when**: Done developing for the day or switching to production

### Production Environment

#### `pixi run prod`
- **Purpose**: Start the production backend in Docker
- **Environment**: `.env` (production Supabase)
- **Port**: 8001
- **Use when**: Testing your app against real Supabase credentials before cloud deployment
- **What it does**: 
  1. Builds Docker image with production mode flag
  2. Starts `backend-prod` container
  3. Runs comprehensive health checks
  4. Seeds supported sources (one-time)
- **⚠️ Warning**: Uses production database—be careful with changes!

#### `pixi run prod-stop`
- **Purpose**: Stop the production backend container
- **Cleanup**: Removes the `backend-prod` container
- **Use when**: Done testing against production or temporarily stopping the server

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
  - Tracks applied migrations in `public.schema_migrations` table
  - Skips already-applied migrations automatically

#### `pixi run apply-migrations-prod`
- **Purpose**: Apply SQL migrations to production Supabase database
- **Environment**: `.env`
- **Use when**: Setting up or updating production Supabase schema
- **⚠️ Warning**: Directly modifies production database—ensure backups exist!
- **Notes**: Same as `apply-migrations` but reads credentials from `.env`

#### `pixi run seed`
- **Purpose**: Run development seed scripts
- **Behavior**: 
  - Auto-detects running Docker container (`backend-dev`)
  - Runs inside Docker if container exists
  - Runs locally using Python venv if container not running
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
- **Purpose**: Run unit tests first, then non-unit tests
- **Environment**: `.env.test` (Supabase test project)
- **Database**:
  - Unit phase avoids DB-backed fixtures entirely
  - Non-unit phase uses per-test `clean_database` resets for DB-backed fixtures
- **Use when**:
  - Validating code changes
  - Running CI/CD locally before pushing
  - Development workflow
- **Notes**: 
  - Composes `pixi run test-unit` then `pixi run test-integration`
  - Non-unit tests still require `SUPABASE_URL` and `SUPABASE_KEY` in `.env.test`
  - CI/CD should prefer this command for full validation

#### `pixi run test-unit`
- **Purpose**: Run only tests marked `unit`
- **Environment**: `.env.test`
- **Database**: No DB reset path is needed for unit-only tests
- **Use when**:
  - Fast local feedback
  - Verifying offline-safe/unit-only changes
  - Running in restricted CI/firewalled environments

#### `pixi run test-integration`
- **Purpose**: Run all tests not marked `unit`
- **Environment**: `.env.test`
- **Database**: DB-backed fixtures reset and reseed per test via `clean_database`
- **Use when**:
  - Validating DB-backed API behavior
  - Exercising seeded fixtures and authenticated flows
  - Running the slower integration half of the suite

#### `pixi run test-fresh`
- **Purpose**: Restore the test DB snapshot, then run unit and non-unit tests
- **Environment**: `.env.test`
- **Use when**:
-  - You need a clean test baseline before a full run
-  - Tracking flaky failures caused by leftover DB state
### Direct Server

#### `pixi run serve`
- **Purpose**: Run FastAPI uvicorn server directly (no Docker)
- **Environment**: `.env.test`
- **Host**: `127.0.0.1`
- **Port**: 8000
- **Workers**: 4
- **Use when**:
  - Developing without Docker containerization
  - Debugging with local IDE breakpoints
  - Rapid iteration on code changes
- **Requirements**:
  - Pixi environment activated: `pixi shell`
  - Supabase test project running/accessible
- **Notes**: 
  - Not for production deployment (use Docker for that)
  - Reload on code changes enabled automatically with uvicorn

## Environment Variables

### `.env.test` (Development/Testing)
Used by: `dev`, `dev-seed`, `dev-reset`, `test`, `serve`, `seed`, `apply-migrations`

Contains:
- Supabase test project credentials
- Test OAuth credentials (GitHub, Ravelry, etc.)
- Test mode flags

### `.env` (Production)
Used by: `prod`, `apply-migrations-prod`

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

### Docker container already running
```bash
# Kill orphaned containers
docker ps -a | grep a11yhood
docker rm -f <container-id>

# Then try again
pixi run dev
```

### Port already in use
```bash
# Find and kill process on port
sudo lsof -i :8002
kill -9 <PID>

# Or use different port (if script supports it)
./scripts/start-dev.sh --port 8003
```

### Need to switch between dev/prod quickly
```bash
# Stop dev, start prod
pixi run dev-stop && pixi run prod

# Stop prod, start dev
pixi run prod-stop && pixi run dev
```

### Viewing Docker logs
```bash
# Dev backend
docker logs -f backend-dev

# Prod backend  
docker logs -f backend-prod

# Both (in separate terminals)
docker logs -f backend-dev &
docker logs -f backend-prod &
```

## Configuration Details

### Shell Scripts Used By Pixi

Pixi tasks wrap these helper shell scripts (still in `scripts/`):
- `start-dev.sh` — Complex Docker setup for dev with reset/seed options
- `start-prod.sh` — Production mode validation and startup  
- `apply-migrations.sh` — PostgreSQL migration runner with tracking
- `seed.sh` — Seed coordinator (Docker or local Python)

These are implementation details; use `pixi run <task>` instead of calling `./scripts/<script>` directly.

**Removed scripts** (replaced by pixi tasks):
- ~~`stop-dev.sh`~~ → Use `pixi run dev-stop`
- ~~`stop-prod.sh`~~ → Use `pixi run prod-stop`
- ~~`run-tests.sh`~~ → Use `pixi run test`

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
