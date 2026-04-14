# Local Testing Guide

This guide helps you run a fully functional local version of a11yhood for testing and development.
Run commands from the repo root unless noted otherwise.

## Prerequisites

- **Python 3.9+**: Backend development
- **uv**: Python package manager (`pip install uv`)
- **Supabase test project**: Credentials for the `a11yhood-test` database in the `make4all-test` org

## Quick Start

### Configure test environment

Copy the example file and fill in your test Supabase credentials:

```bash
cp .env.test.example .env.test
# Edit .env.test and set SUPABASE_URL, SUPABASE_KEY, SUPABASE_ANON_KEY
```

### Start the backend

```bash
export $(cat .env.test | grep -v '^#' | xargs)
uv run python -m uvicorn main:app --reload --port 8000
```

## Accessing the Application

| Component | URL | Purpose |
|-----------|-----|---------|
| Backend API | http://localhost:8000 | API endpoints |
| API Docs | http://localhost:8000/docs | Interactive API documentation |

## Test Users

The `.env.test` configuration uses the `a11yhood-test` Supabase database with pre-seeded test users:

| Username | User ID | Role | Use Case |
|----------|---------|------|----------|
| `admin_user` | 49366adb-... | Admin | Full system access, scraper controls |
| `moderator_user` | 94e116f7-... | Moderator | Content moderation, user management |
| `regular_user` | 2a3b7c3e-... | User | Regular user features, submit products |

## Test Database (Supabase)

The application always uses Supabase. The `.env.test` file points at the `a11yhood-test` test project.

### Apply Migrations (Schema Setup)

Schema is not auto-applied by app startup or pytest. Apply all SQL migrations before seeding/tests:

```bash
# Option 1: put SUPABASE_DB_URL in .env.test
./scripts/apply-migrations.sh

# Option 2: run against production/staging env file
./scripts/apply-migrations.sh --env-file .env

# Option 3: pass DB URL directly
SUPABASE_DB_URL='postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require' \
	./scripts/apply-migrations.sh
```

The script applies all `migrations/*.sql` files in timestamp order and tracks applied files in
`public.schema_migrations`, so re-running is safe.

### Seed Test Data

```bash
export $(cat .env.test | grep -v '^#' | xargs)
uv run python seed_scripts/seed_all.py
```

Or run individual scripts:

```bash
uv run python seed_scripts/seed_supported_sources.py
uv run python seed_scripts/seed_scraper_search_terms.py
uv run python seed_scripts/seed_test_users.py
uv run python seed_scripts/seed_test_product.py
uv run python seed_scripts/seed_test_collections.py
```

### Reset Test Data

To wipe all test data and start fresh, connect to the `a11yhood-test` Supabase project via the
SQL editor and truncate the tables, or use the DatabaseAdapter cleanup in a Python shell:

```bash
export $(cat .env.test | grep -v '^#' | xargs)
uv run python - << 'EOF'
from config import get_settings
from database_adapter import DatabaseAdapter
db = DatabaseAdapter(get_settings())
db.cleanup()
print("All test data deleted.")
EOF
```

Then re-seed with `uv run python seed_scripts/seed_all.py`.

## Testing Features

### Backend Tests

```bash
# Run all tests (requires .env.test with valid Supabase credentials)
uv run pytest tests/ -v

# Run unit tests only (excludes integration tests)
uv run pytest tests/ -v -m "not integration"

# Run specific test file
uv run pytest tests/test_products.py -v

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html
```

## Environment Variables

### Backend (`.env.test`)

```env
# Test Supabase project (make4all-test org / a11yhood-test database)
SUPABASE_URL=https://your-test-project.supabase.co
SUPABASE_KEY=your-test-service-role-key
SUPABASE_ANON_KEY=your-test-anon-key

# Test mode (enables dev tokens for authentication)
TEST_MODE=true
TEST_SCRAPER_LIMIT=5

# GitHub OAuth (optional for tests)
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Secret key (can be any random string for tests)
SECRET_KEY=your-random-secret-key-for-testing
```

## Troubleshooting

### "SUPABASE_URL must be configured" error

Ensure `.env.test` exists with valid Supabase credentials. Copy from `.env.test.example`:

```bash
cp .env.test.example .env.test
# Fill in credentials from the Supabase dashboard
```

### Tests are skipped

If you see `SKIPPED ... SUPABASE_URL and SUPABASE_KEY are required`, your `.env.test`
is missing valid Supabase credentials. See above.

### Tests failing locally but passing in CI

1. Make sure you've run `uv sync`
2. Check `.env.test` exists with correct Supabase credentials
3. Verify your test Supabase project has the latest schema applied

### Port 8000 already in use

```bash
uv run python -m uvicorn main:app --port 8001
```

## Need Help?

- Check existing docs via the [documentation index](README.md)
- Review test examples in `tests/`
- Run with verbose logging: `uv run pytest tests/ -v --log-cli-level=DEBUG`
