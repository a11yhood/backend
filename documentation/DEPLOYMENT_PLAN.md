# a11yhood Deployment Plan

## Overview

This document outlines the phased approach to deploying a11yhood from a test environment to production. The deployment strategy follows these stages:

1. **Stage 1**: Local deployment with production Supabase (current stage)
2. **Stage 2**: Cloud deployment 

## Current State

- **Test Environment**: Dedicated Supabase test project (`.env.test`) for development/testing
- **Test Scripts**: `./start-dev.sh` with `.env.test` configuration
- **Test Data**: Seeded users, products, and sources for consistent testing
- **All tests passing**: 198/198

## Stage 1: Local Deployment with Production Supabase

**Goal**: Run backend locally but connect to the production Supabase database. This validates the backend against real data before cloud deployment.

### Prerequisites

1. **Supabase Production Project**
   - Create production Supabase project at https://supabase.com
   - Note project URL and keys (service_role and anon keys)
   - Apply schema from `supabase-schema.sql`

2. **OAuth Credentials** (if using GitHub/Ravelry/Thingiverse auth)
   - GitHub OAuth: See [GITHUB_AUTH_SETUP.md](GITHUB_AUTH_SETUP.md)
   - Ravelry OAuth: See [RAVELRY_SETUP.md](RAVELRY_SETUP.md)
   - Thingiverse OAuth: See [THINGIVERSE_SETUP.md](THINGIVERSE_SETUP.md)

3. **SSL Certificates** (for HTTPS in development)
   - Already generated: `localhost+2.pem` and `localhost+2-key.pem` (in repo root)
   - These enable HTTPS on localhost for OAuth redirect compatibility

### Configuration Files

#### Backend Production Environment (`.env`)

Create `.env` from `.env.test.example`:

```bash
cp .env.test.example .env
```

Edit `.env` with production values:

```dotenv
# Production Supabase Database
SUPABASE_URL=https://your-production-project.supabase.co
SUPABASE_KEY=your-production-service-role-key
SUPABASE_ANON_KEY=your-production-anon-key

# CORS Configuration - Local deployment still uses localhost
FRONTEND_URL=https://localhost:5173
PRODUCTION_URL=https://a11yhood.com  # Your future production domain

# Production mode (not test mode)
TEST_MODE=false
# TEST_SCRAPER_LIMIT not needed in production

# GitHub OAuth (production credentials)
GITHUB_CLIENT_ID=your-production-github-client-id
GITHUB_CLIENT_SECRET=your-production-github-client-secret

# GitHub API token for higher rate limits
GITHUB_TOKEN=your-github-personal-access-token

# Secret key for JWT - GENERATE NEW RANDOM KEY
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-random-production-secret-key-64-chars

```dotenv
# Production Supabase Configuration
VITE_SUPABASE_URL=https://your-production-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-production-anon-key

# API URL (local deployment)
VITE_API_URL=http://localhost:8000

# Production environment flag
VITE_ENV=production
```

### Deployment Scripts

#### `start-prod.sh` - Start Local Production Environment

**Purpose**: Start  backend in production mode (local servers, production database)

**Features**:
- Uses `.env` (production Supabase)
- No database reset option (preserves production data)
- Includes health checks and startup verification

**Usage**:
```bash
./start-prod.sh
```

#### `stop-prod.sh` - Stop Local Production Environment

**Purpose**: Cleanly shutdown production servers

**Usage**:
```bash
./stop-prod.sh
```

### Migration Steps

#### 1. Set Up Production Supabase

```bash
# 1. Create Supabase project at https://supabase.com
# 2. Navigate to Settings → API and copy:
#    - Project URL
#    - anon/public key
#    - service_role key (keep secret!)

# 3. Apply schema to production database
# Option A: Using Supabase SQL Editor
#    - Open https://supabase.com/dashboard/project/YOUR_PROJECT/sql
#    - Paste contents of supabase-schema.sql
#    - Run


#### 2. Configuration for Production

```bash
# Create and configure  .env
cp .env.test.example .env

# Edit .env with your production Supabase credentials
# CRITICAL: Generate new SECRET_KEY for production
python -c "import secrets; print(secrets.token_hex(32))"

# Verify configuration
ENV_FILE=.env uv run python -c "from config import settings; print(f'DB: {settings.SUPABASE_URL}')"
```

#### 3. Seed Production Data

```bash
# Seed supported sources (GitHub, Ravelry, Thingiverse, etc.)
ENV_FILE=.env uv run python seed_supported_sources.py

# Optional: Seed initial products (or let users submit)
# ENV_FILE=.env uv run python seed_test_product.py

# Note: Do NOT run seed_test_users.py in production
# Users will be created via real GitHub OAuth
```

#### 5. Start Local Production Environment

```bash
# From repo root
./start-prod.sh

# Verify services:
# - Backend API: http://localhost:8000/docs
```

#### 6. Verify Production Deployment

**Backend Health Check**:
```bash
# Check API is running
curl http://localhost:8000/health

# Check database connection
curl http://localhost:8000/api/sources/supported

# Expected: List of supported sources (GitHub, Ravelry, etc.)
```


**Database Verification**:
```bash
# Open Supabase dashboard
# Navigate to Table Editor
# Verify tables exist:
# - users
# - products
# - ratings
# - reviews
# - discussions
# - collections
# - product_urls
# - sources
# - supported_sources
# - activities
# - blog_posts
```

### Troubleshooting

#### Backend won't start

```bash
# Check .env file exists and has correct values
cat .env | grep SUPABASE_URL

# Check Supabase connection
ENV_FILE=.env uv run python -c "
from config import settings
from database_adapter import DatabaseAdapter
adapter = DatabaseAdapter()
print('Connection successful!')
"

# Check for port conflicts
lsof -i :8000
```

#### OAuth login fails

```bash
# Verify OAuth credentials in backend/.env
# Check GitHub OAuth app settings:
# - Authorization callback URL: https://localhost:5173/auth/callback
# - Homepage URL: https://localhost:5173

# Check browser console for specific error messages
# Common issues:
# - Wrong redirect URI
# - Missing HTTPS (OAuth requires HTTPS)
# - Invalid client ID/secret
```

#### Database permissions errors

```bash
# Verify you're using service_role key in backend/.env
# (not anon key - anon key has RLS restrictions)

# Check Supabase logs:
# Dashboard → Logs → Postgres Logs

# Verify RLS policies allow operations
# Dashboard → Authentication → Policies
```

### Security Considerations

1. **Never commit `.env` or `.env.local` files**
   - These contain production secrets
   - Already in `.gitignore`
   - Share securely via password manager or encrypted channel

2. **Rotate secrets regularly**
   - Generate new SECRET_KEY every 90 days
   - Rotate OAuth client secrets annually
   - Update Supabase service_role key if compromised

3. **Use HTTPS in production**
   - Local development uses HTTPS via mkcert
   - Cloud deployment MUST use HTTPS (Let's Encrypt, Cloudflare, etc.)

4. **Restrict CORS origins**
   - Update `FRONTEND_URL` and `PRODUCTION_URL` in backend/.env
   - Never use wildcards (*) in production

5. **Monitor Supabase usage**
   - Check Dashboard → Settings → Usage
   - Set up alerts for unusual activity
   - Review Postgres logs for suspicious queries

### Switching Between Test and Production

The application supports running in both test (Supabase test project) and production (Supabase production project) modes:

**Test Environment** (development, CI/CD):
```bash
./start-dev.sh   # Uses .env.test, Supabase test project, seeded data
./run-tests.sh   # Runs all tests against Supabase test project
```

**Production Environment** (local with production DB):
```bash
./start-prod.sh  # Uses .env, Supabase, real OAuth
./stop-prod.sh   # Clean shutdown
```

**Key Differences**:
| Aspect | Test Environment | Production Environment |
|--------|-----------------|----------------------|
| Backend Config | `.env.test` | `.env` |
| Database | Supabase test project | Supabase PostgreSQL |
| Users | Seeded test users | Real GitHub OAuth |
| OAuth | Mock/bypass | Real GitHub/Ravelry/etc |
| Data | Ephemeral (can reset) | Persistent (production) |
| HTTPS | Yes (localhost SSL) | Yes (localhost SSL) |

## Stage 2: Cloud Deployment (Future)

Once Stage 1 is validated, the next phase will deploy to cloud infrastructure:

### Not Changing in Cloud Deployment

- Database: Supabase (same instance, just accessed from cloud servers)
- Code: Same codebase, just running on cloud servers instead of localhost
- OAuth: Same credentials (just update redirect URIs to production domain)

## Monitoring and Maintenance

### Health Checks

**Backend**:
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

curl http://localhost:8000/api/sources/supported
# Expected: Array of supported sources
```

### Logs

**Backend Logs**:
```bash
# Live tail
tail -f backend.log

# Recent errors
grep ERROR backend.log | tail -n 20
```

**Supabase Logs**:
- Dashboard → Logs → Postgres Logs
- Dashboard → Logs → API Logs
- Dashboard → Logs → Auth Logs

### Backup and Recovery

**Supabase Backups**:
- Automatic daily backups (retained based on plan)
- Manual backups: Dashboard → Settings → Database → Backup

**Local Backups** (for Stage 1):
```bash
# Export data via API (custom script)
# Or use Supabase CLI: supabase db dump
```

**Recovery**:
```bash
# Restore from Supabase backup
# Dashboard → Settings → Database → Restore

# Or use SQL dump
# psql -h db.PROJECT.supabase.co -U postgres -d postgres < backup.sql
```

## Testing Production Configuration Locally

Before deploying to cloud, thoroughly test the production configuration locally:

### 1. Test Suite Against Production DB

```bash
# WARNING: This will create test data in production DB
# Only do this on a separate test Supabase project, not production!

# Run backend tests against Supabase
ENV_FILE=.env.prod uv run pytest

**Recommendation**: Create a separate "staging" Supabase project for testing production configuration without affecting real production data.

### 2. Manual QA Checklist

Follow [QA_TESTING_GAPS.md](QA_TESTING_GAPS.md) for comprehensive manual testing:

- [ ] User authentication (GitHub OAuth)
- [ ] Product submission and editing
- [ ] Rating and review system
- [ ] Discussion threads (nested replies)
- [ ] Collections (create, edit, delete)
- [ ] User profile and stats
- [ ] Admin/moderator functions
- [ ] Performance (load 100+ products)
- [ ] Security (authorization checks, IDOR prevention)

### 3. Performance Testing

```bash
# Load testing with Apache Bench
ab -n 1000 -c 10 http://localhost:8000/api/products
```

### 4. Security Testing

- [ ] Run security audit: `npm audit` (frontend) and `uv run pip-audit` (backend)
- [ ] Check HTTPS certificate (should be valid for localhost)
- [ ] Verify CORS restrictions (test from different origin)
- [ ] Test authorization bypass attempts
- [ ] Check SQL injection vectors (Supabase should prevent)
- [ ] Verify secrets are not exposed in responses or logs

## Rollback Plan

If issues arise in production:

### Immediate Rollback (Stage 1)

```bash
# Stop production servers
./stop-prod.sh

# Restart test environment
./start-dev.sh

# Or if deployed to cloud: revert to previous git tag/commit
git revert HEAD
git push
# (Triggers re-deploy on most platforms)
```

### Database Rollback

**Supabase**:
1. Dashboard → Settings → Database → Backups
2. Select backup before issue occurred
3. Restore
4. Verify data integrity

**Note**: Rolling back code but not database can cause schema mismatches. Always test rollback procedures in staging first.

## Next Steps

1. **Complete Stage 1 Setup**
   - Set up production Supabase project
   - Create `.env` and `.env.local` files
   - Test local production deployment

2. **Validate Stage 1**
   - Run full test suite against production DB (on staging project)
   - Complete manual QA checklist
   - Fix any issues found

3. **Document Stage 1 Results**
   - Update this document with any lessons learned
   - Document any additional configuration needed
   - Note performance metrics and benchmarks

4. **Plan Stage 2** (when ready)
   - Choose cloud hosting provider
   - Set up CI/CD pipeline
   - Configure monitoring and alerting
   - Create detailed cloud deployment guide

## Related Documentation

- [AGENT_GUIDE.md](AGENT_GUIDE.md) - Development conventions and quick commands
- [LOCAL_TESTING.md](LOCAL_TESTING.md) - Local test environment setup
- [QA_TESTING_GAPS.md](QA_TESTING_GAPS.md) - Manual testing checklist
- [SECURITY_BEST_PRACTICES.md](SECURITY_BEST_PRACTICES.md) - Security guidelines
- [DATABASE.md](DATABASE.md) - Database architecture and operations
- [OAUTH_SETUP.md](OAUTH_SETUP.md) - OAuth configuration for all providers
