# Quick Reference: Test vs Production Environments

This guide helps you quickly switch between test and production environments.

## At a Glance

| Command | Environment | Database | OAuth | Purpose |
|---------|------------|----------|-------|---------|
| `pixi run dev` | Test | Supabase (test) | Mock | Development & testing |
| `pixi run prod` | Production | Supabase (production) | Real | Production validation (local) |
| `pixi run test` | Test | Supabase (test) | Mock | Run automated tests |

## Test Environment (Development)

**Use when**: Developing features, running tests, making database changes

**Start**: `pixi run dev`  
**Stop**: `pixi run dev-stop`

**Configuration**:
- Backend: `.env.test`

**Database**: Supabase test instance (`a11yhood-test` in `make4all-test` org)

**Users**: Seeded test users (admin_user, moderator_user, regular_user)

**OAuth**: Mock GitHub OAuth (dev tokens accepted when TEST_MODE=true)

**Features**:
- Deterministic test data
- Test data seeded via `seed_scripts/seed_all.py`
- Safe to experiment - test database is separate from production

## Production Environment (Local with Production DB)

**Use when**: Testing against real Supabase, validating before cloud deployment

**Start**: `pixi run prod`  
**Stop**: `pixi run prod-stop`

**Configuration**:
- Backend: `.env`

**Database**: Production Supabase (PostgreSQL in cloud)

**Users**: Real GitHub OAuth (any GitHub user can log in)

**OAuth**: Real GitHub/Ravelry/Thingiverse OAuth

**Features**:
- Same codebase as cloud deployment
- Tests full authentication flow
- Persistent data (survives restarts)
- **⚠️ WARNING**: All changes are permanent!

## Setup Checklist

### Test Environment ✅ (Already set up)

- [x] `.env.test` exists
- [x] Test users seeded
- [x] Supported sources seeded
- [x] All tests passing (198 backend)

### Production Environment (To Do)

- [ ] Create production Supabase project
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in Supabase credentials in `.env`
- [ ] Generate new SECRET_KEY for production
- [ ] Set up GitHub OAuth app (production)
- [ ] Apply `supabase-schema.sql` to Supabase database
- [ ] Run `pixi run prod` to test

See [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) for detailed instructions.

## Common Tasks

### Reset Test Database

```bash
pixi run dev-reset
```

### Run Tests

```bash
# tests (don't need servers running)
pixi run test
```

### Switch from Test to Production

```bash
# Stop test environment
pixi run dev-stop

# Start production environment
pixi run prod
```

### View Logs

```bash
#  logs (both test and production)
tail -f backend.log

```

### Check Running Servers

```bash
# Check if backend is running
curl http://localhost:8002/health


# See what's listening on ports
lsof -i :8002    # Dev backend
lsof -i :8001    # Prod backend

```

### Emergency Stop (if scripts don't work)

```bash
# Kill all uvicorn processes
pkill -f uvicorn

# Kill all vite/npm processes
pkill -f vite
pkill -f "npm.*dev"

# Nuclear option: kill by port
kill $(lsof -t -i:8000)  # Backend

```

## Configuration Files

### Backend

| File | Purpose | Tracked in Git? |
|------|---------|----------------|
| `.env.test` | Test environment | ✅ Yes (safe - no secrets) |
| `.env.test.example` | Template for test env | ✅ Yes |
| `.env` | Production environment | ❌ No (.gitignore) |
| `.env.example` | Template for production | ✅ Yes |


## Key Differences

| Aspect | Test Environment | Production Environment |
|--------|-----------------|----------------------|
| **Database** | Supabase test project | Supabase production project |
| **Data** | Ephemeral, can reset | Persistent, permanent |
| **Users** | Seeded test users | Real GitHub OAuth |
| **OAuth** | Mock (dropdown) | Real (GitHub redirect) |
| **Secrets** | Safe defaults | Real secrets required |
| **Internet** | Required (Supabase test) | Required (Supabase prod) |
| **Speed** | Network-dependent | Network-dependent |
| **Cost** | Free | Supabase usage fees |

## Environment Variables

### Critical Backend Variables

| Variable | Test Value | Production Value |
|----------|-----------|-----------------|
| `ENV_FILE` | `.env.test` | `.env` |
| `SUPABASE_URL` | Test Supabase URL | Production Supabase URL |
| `SUPABASE_KEY` | Test service role key | Production service role key |
| `TEST_MODE` | `true` | `false` |
| `SECRET_KEY` | Dev default | **Generate new!** |
| `GITHUB_CLIENT_ID` | (optional for test) | Required for auth |


## Troubleshooting

### "Backend won't start"

```bash
# Check if .env.test exists (for test) or .env (for production)
ls -la .env*

# Check if port is already in use
lsof -i :8002

# Kill existing backend and try again
pkill -f uvicorn
pixi run dev  # or pixi run prod
```

### "OAuth not working"

**Test Environment**:
- Uses dev tokens (dev-token-<user_id>) when TEST_MODE=true
- No real GitHub OAuth needed

**Production Environment**:
- Verify `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in `.env`
- Check OAuth app settings at https://github.com/settings/developers
- Authorization callback URL should be: `https://localhost:5173/auth/callback`
- Homepage URL should be: `https://localhost:5173`

### "Database connection failed"

**Test Environment**:
- Verify `SUPABASE_URL` and `SUPABASE_KEY` are set in `.env.test`
- Check Supabase test project is active at https://supabase.com/dashboard
- Run: `uv run python -c "from config import get_settings; from database_adapter import DatabaseAdapter; db = DatabaseAdapter(get_settings()); print(db.table('users').select('id').limit(1).execute())"`

**Production Environment**:
- Verify `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Check Supabase project is active at https://supabase.com/dashboard

### "Tests failing"

```bash
# Make sure SUPABASE credentials are in .env.test
cat .env.test | grep SUPABASE

# Seed test data
uv run python seed_scripts/seed_all.py

# Run specific test file
uv run pytest tests/test_products.py -v
```

## Quick Commands Reference

```bash
# Start development environment (test)
./start-dev.sh

# Start development with fresh database
./start-dev.sh --reset-db

# Start production environment (local + Supabase)
./start-prod.sh

# Stop any environment
pixi run dev-stop   # or pixi run prod-stop

# Run all backend tests
pixi run test

# Run specific test file
cd backend && uv run pytest tests/test_products.py


# Check API documentation
open http://localhost:8000/docs

# View application
open https://localhost:5173

# Monitor logs
tail -f backend.log 

# Check what's running
ps aux | grep -E "uvicorn|vite"

# Kill everything
./stop-dev.sh && pkill -f uvicorn && pkill -f vite
```

## Security Reminders

### Test Environment

- ✅ Safe to commit `.env.test` (no real secrets)
- ✅ Safe to share test database
- ✅ Safe to reset database anytime

### Production Environment

- ❌ **NEVER** commit `.env` or `.env.local`
- ❌ **NEVER** share `SECRET_KEY` or `SUPABASE_KEY`
- ❌ **NEVER** reset production database
- ✅ Generate new `SECRET_KEY` for production
- ✅ Use different OAuth credentials for production
- ✅ Keep production Supabase keys secure

## Next Steps

1. **If you're developing**: Use test environment (`./start-dev.sh`)
2. **If you're ready to deploy**: Follow [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)
3. **If you're testing**: Run `pixi run test`
4. **If something breaks**: Check logs (`tail -f *.log`) and try `./start-dev.sh --reset-db`

## Related Documentation

- [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) - Full deployment guide
- [LOCAL_TESTING.md](LOCAL_TESTING.md) - Local development setup
- [AGENT_GUIDE.md](AGENT_GUIDE.md) - Development conventions
- [DATABASE.md](DATABASE.md) - Database architecture
- [OAUTH_SETUP.md](OAUTH_SETUP.md) - OAuth configuration
