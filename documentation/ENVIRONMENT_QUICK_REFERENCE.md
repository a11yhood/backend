# Quick Reference: Test vs Production Environments

This guide helps you quickly switch between test and production environments.

## At a Glance

| Command | Environment | Database | OAuth | Purpose |
|---------|------------|----------|-------|---------|
| `./start-dev.sh` | Test | Supabase test project | Mock | Development & testing |
| `./start-prod.sh` | Production | Supabase | Real | Production validation (local) |
| `./run-tests.sh` | Test | Supabase test project | Mock | Run automated tests |

## Test Environment (Development)

**Use when**: Developing features, running tests, making database changes

**Start**: `./start-dev.sh`  
**Stop**: `./stop-dev.sh`

**Configuration**:
- Backend: `.env.test`

**Database**: Supabase test project from `.env.test`

**Users**: Seeded test users (admin_user, moderator_user, regular_user)

**OAuth**: Mock GitHub OAuth (select test user from dropdown)

**Features**:
- Fast database reset (`./start-dev.sh --reset-db`)
- Deterministic test data
- Safe to experiment - data is ephemeral

## Production Environment (Local with Production DB)

**Use when**: Testing against real Supabase, validating before cloud deployment

**Start**: `./start-prod.sh`  
**Stop**: `./stop-prod.sh`

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
- [ ] Run `./start-prod.sh` to test

See [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) for detailed instructions.

## Common Tasks

### Reset Test Database

```bash
./start-dev.sh --reset-db
```

### Run Tests

```bash
# tests (don't need servers running)
./run-tests.sh 
```

### Switch from Test to Production

```bash
# Stop test environment
./stop-dev.sh

# Start production environment
./start-prod.sh
```

### View Logs

```bash
#  logs (both test and production)
tail -f backend.log

```

### Check Running Servers

```bash
# Check if backend is running
curl http://localhost:8000/health


# See what's listening on ports
lsof -i :8000    # Backend

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
| **Internet** | Required | Required |
| **Speed** | Network-backed | Network-backed |
| **Cost** | Free | Supabase usage fees |

## Environment Variables

### Critical Backend Variables

| Variable | Test Value | Production Value |
|----------|-----------|-----------------|
| `ENV_FILE` | `.env.test` | `.env` |
| `SUPABASE_URL` | `https://test-project.supabase.co` | `https://prod-project.supabase.co` |
| `SUPABASE_KEY` | Test service role key | Service role key |
| `TEST_MODE` | `true` | `false` |
| `SECRET_KEY` | Dev default | **Generate new!** |
| `GITHUB_CLIENT_ID` | (optional for test) | Required for auth |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | `api.yourdomain.com,*.vercel.app` |


## Troubleshooting

### "Backend won't start"

```bash
# Check if .env exists (for production) or .env.test (for test)
ls -la .env*

# Check if port is already in use
lsof -i :8000

# Kill existing backend and try again
pkill -f uvicorn
./start-dev.sh  # or ./start-prod.sh
```

### "OAuth not working"

**Test Environment**:
- OAuth is mocked - just select a user from dropdown
- No real GitHub OAuth needed

**Production Environment**:
- Verify `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in `.env`
- Check OAuth app settings at https://github.com/settings/developers
- Authorization callback URL should be: `https://localhost:5173/auth/callback`
- Homepage URL should be: `https://localhost:5173`

### "Database connection failed"

**Test Environment**:
- Verify `.env.test` points to the intended test project
- Reset from snapshot: `pixi run reset`
- Restart: `./start-dev.sh`

**Production Environment**:
- Verify `SUPABASE_URL` and `SUPABASE_KEY` in `.env`
- Check Supabase project is active at https://supabase.com/dashboard
- Verify network connectivity: `ping db.YOUR_PROJECT.supabase.co`
- Check Supabase logs for connection errors

### "Tests failing"

```bash
# Make sure you're using test environment
./stop-prod.sh
./start-dev.sh

# Reset database and try again
pixi run reset
./run-tests.sh
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
./stop-dev.sh   # or ./stop-prod.sh

# Run all backend tests
./run-tests.sh backend

# Run specific test file
pixi run pytest tests/test_products.py


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
3. **If you're testing**: Run `./run-tests.sh  `
4. **If something breaks**: Check logs (`tail -f *.log`) and try `./start-dev.sh --reset-db`

## Related Documentation

- [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) - Full deployment guide
- [LOCAL_TESTING.md](LOCAL_TESTING.md) - Local development setup
- [AGENT_GUIDE.md](AGENT_GUIDE.md) - Development conventions
- [DATABASE.md](DATABASE.md) - Database architecture
- [OAUTH_SETUP.md](OAUTH_SETUP.md) - OAuth configuration
