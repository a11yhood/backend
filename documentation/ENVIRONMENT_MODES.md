# a11yhood Environment Modes Guide

We operate three environments, separated by env files and behavior flags:

- Dev/Test (Supabase test project, seeded): `.env.test`, uses dedicated test Supabase data, seeded fixtures, dev-token auth, safe to reset.
- Production (local, Supabase): `.env`, connects to production Supabase, real OAuth, no seeding.
- Deploy (external host, Supabase): same as Production but running on the external server; `.env` holds production Supabase and OAuth secrets, no seeding.

`ENV_FILE` selects the mode used by [config.py](config.py):

```bash
ENV_FILE=.env.test  # Dev/Test
ENV_FILE=.env       # Production/Deploy
```

## Dev/Test (Supabase Test Project + Seeds)

Setup
```bash
cp .env.test.example .env.test  # if missing
```

Start Dev/Test
```bash
./start-dev.sh --seed
```

What happens
- Exports `ENV_FILE=.env.test`
- Connects to the dedicated Supabase test project
- Runs `seed_scripts/seed_all.py` (test users/products/collections, search terms)
- Uses `TEST_MODE=true` behavior (dev tokens, no scheduled scrapers)

Running tests
```bash
./run-tests.sh
```
Tests always set `ENV_FILE=.env.test` and run against the Supabase test project.

Stop
```bash
./stop-dev.sh
```

## Production (Local with Supabase)

Setup
```bash
cp .env.test.example .env  # if missing
```
Fill `.env` with Supabase and OAuth secrets. See [DEPLOYMENT_PLAN.md](documentation/DEPLOYMENT_PLAN.md) and [AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) for required values.

Start Production
```bash
./start-prod.sh
```
Uses `ENV_FILE=.env`, connects to Supabase, and does not seed.

Verify
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/sources/supported
```

Stop
```bash
./stop-prod.sh
```

## Deploy (External Host with Supabase)

- Same settings as Production but running on the external server.
- Ensure `.env` on the host points to the production Supabase project and real OAuth secrets.
- Do **not** seed in this environment.

## Switching Between Modes

Dev/Test → Production
```bash
./stop-dev.sh
./start-prod.sh
```

Production → Dev/Test
```bash
./stop-prod.sh
./start-dev.sh --seed
```

## Safety Checks

- Confirm the active env: `echo $ENV_FILE` (`.env.test` for Dev/Test, `.env` for Production/Deploy).
- Confirm test mode intent: `.env.test` should use `TEST_MODE=true`.
- If seeding fails in Dev/Test, rerun `./start-dev.sh --seed` after ensuring `.env.test` exists.

## Related Documentation

- [AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) – Development conventions and commands
- [DEPLOYMENT_PLAN.md](documentation/DEPLOYMENT_PLAN.md) – Production setup and OAuth configuration
- [LOCAL_TESTING.md](documentation/LOCAL_TESTING.md) – Local setup and testing procedures
- [ENVIRONMENT_QUICK_REFERENCE.md](documentation/ENVIRONMENT_QUICK_REFERENCE.md) – Quick reference
- [config.py](config.py) – How `ENV_FILE` is loaded
