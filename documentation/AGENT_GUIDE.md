# Agent Guide

Read this first when operating on the repo. It summarizes conventions, helper utilities, and must-read docs.

## Key Conventions
- Prefer existing helpers over reimplementing logic; avoid direct DB access when a wrapper exists.
- Integration/system tests should not mock application internals; use real API calls and real test DB state.
- Unit tests may use `monkeypatch`/`unittest.mock` for isolated logic.
- When adding features, update coverage docs so tests map to behavior.
- Default to snake_case

## Environment Modes (read before running anything)
- **Dev/Test (Supabase test project + seeds):** `./start-dev.sh --seed` loads `.env.test`, connects to the shared test Supabase project, and seeds data via `seed_scripts/seed_all.py`. Safe for local work and scrapers; no real OAuth.
- **Production (local Supabase):** `./start-prod.sh` loads `.env`, connects to the real Supabase backend, no seeding. Use for local QA against real data.
- **Deploy (external server):** Runs the same production settings on the external host; use Supabase service role keys and real OAuth. Do not seed here.

## Git Workflow
- **NEVER run `git commit` or `git push`, create PRs, or perform history-rewrite git actions** unless the user explicitly asks in that turn
- Explicit permission required: wait for a direct user instruction like "commit now" or "push now" before running either command
- You may suggest commit messages or explain what should be committed
- You may run `git add` to stage files when appropriate
- You may run `git status` or `git diff` to check changes
- Focus on making changes and letting the user review and commit them
- Final fixes merge into the main branch; open PRs targeting main unless told otherwise.

### Pre-commit / Pre-push Safety Checklist (Agent)
- Before any `git commit`: show staged files and ask for explicit confirmation
- Before any `git push`: show target remote/branch and ask for explicit confirmation
- If a commit/push happens accidentally: stop, notify the user immediately, and ask whether they prefer revert commit or reset+force-push

## Code Commenting Guidelines
Keep code readable first through clear names and small functions. Use comments to clarify intent or context that code alone cannot convey.

- What to comment:
  - Module/file headers: brief purpose and responsibilities (1–4 lines).
  - Public APIs (exported functions/components/classes): JSDoc/TSDoc for params, returns, side-effects, and non-obvious behavior.
  - Non-obvious logic: tricky algorithms, security assumptions, race conditions, or constraints from external systems/APIs.
  - Accessibility or security notes: call out important a11y roles/flows or permission checks that must not be removed.
- What not to comment:
  - Restating the obvious (e.g., “increment i” or narrating JSX structure).
  - Commenting around dead code—delete it instead; rely on git history.
  - Outdated TODOs. If a follow-up is needed, add a concise TODO with owner/issue link (e.g., `// TODO(jane): link-to-issue`).
- Style:
  - Prefer JSDoc/TSDoc (`/** ... */`) for exported symbols; use `//` line comments for short, local notes.
  - Keep comments adjacent to the code they explain; keep them updated when refactoring.
  - Favor examples over prose when helpful (short snippet > long paragraph).
  - Default to self-documenting code; if you feel the need for long comments, consider refactoring first.

## Timestamp Handling
**CRITICAL: Always use timezone-aware UTC datetimes**

Python's `datetime.utcnow()` is deprecated and will be removed. Always use timezone-aware datetimes:

```python
# ❌ WRONG - deprecated and naive datetime
from datetime import datetime
timestamp = datetime.utcnow()

# ✅ CORRECT - timezone-aware UTC datetime
from datetime import datetime, UTC
timestamp = datetime.now(UTC)

# For database storage (ISO format)
timestamp_str = datetime.now(UTC).isoformat()

# For naive datetime (if required by legacy code)
naive_timestamp = datetime.now(UTC).replace(tzinfo=None)
```

**Key rules:**
- Always import `UTC` from `datetime`: `from datetime, UTC`
- Use `datetime.now(UTC)` for current UTC time
- Use `.isoformat()` when storing timestamps as strings
- Use `.replace(tzinfo=None)` only if interfacing with legacy code that requires naive datetimes
- SQLAlchemy models use naive datetimes internally (see `database_adapter.py`'s `utcnow_naive()` helper)

## Security Defaults
- Enforce authn/authz for every mutating endpoint; never trust client roles or IDs.
- Guard ownership and role checks (admin/moderator/manager) centrally to prevent IDOR.
- Validate and limit all inputs (length, allowlisted schemes for URLs) and escape user content (discussions, reviews) before render.
- Keep secrets in env files (never in git) and avoid logging tokens or PII; prefer HTTPS and strict CORS in non-dev.
- Add negative-path tests when changing contracts (invalid token, wrong role, bad payload) to keep security behavior stable.

## Helper Functions & Patterns
- **Server start scripts**: use `./start-dev.sh --seed` (Supabase test project + seeds) or `./start-prod.sh` (Supabase). On the external host, use the deploy flow with production env vars. Prefer these over manual uvicorn/npm commands unless debugging.
- **Database access**: backend code should go through `database_adapter.py` / services (not direct Supabase client) so request handling stays consistent across environments.
- **Scrapers**: backend handles scraper services/routes; 

### Supabase Database Migrations
- All changes to Supabase schema, RLS policies, triggers, and seed data must be implemented via SQL migrations under `backend/migrations/`.
- Naming: use timestamped filenames, e.g., `YYYYMMDD_add_feature_name.sql`.
- Scope: include `create table`, `alter table`, `enable row level security`, `create policy`, and triggers as needed. Prefer idempotent operations (`create ... if not exists`).
- Application:
  - Local dev: apply migrations to your Supabase project via the Supabase SQL editor or CLI.
  - CI/Prod: ensure migrations are applied before deploying changes that depend on them.
- Do not edit `supabase-schema.sql` directly for new changes; treat it as a consolidated reference. Future changes must be introduced via migrations and then reflected in the schema if needed.
- Example: see `backend/migrations/20251226_add_scraper_search_terms.sql` for adding `scraper_search_terms` with RLS and triggers.

## Testing Expectations
- **Fixtures**: use pytest fixtures for test data setup; tests should use the FastAPI TestClient to make API calls (not direct database operations). Fixtures may insert directly into the database for setup, but test assertions should verify API responses.
- **No direct database operations in tests**: All test operations (create, read, update, delete) should go through the API layer. This ensures tests verify the complete request/response cycle including validation, authorization, and data transformation.


## Required Docs to Read
- [README.md](../README.md) — repo overview and commands.
- [documentation/README.md](README.md) — documentation index.
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md) & [TEST_COVERAGE_MATRIX.md](TEST_COVERAGE_MATRIX.md) — how tests map to features.
- [USER_STORIES_AND_TESTS.md](USER_STORIES_AND_TESTS.md) — expected outcomes per story; update when features change.
- [LOCAL_TESTING.md](LOCAL_TESTING.md) & [QUICK_START.md](QUICK_START.md) — environment and startup.
- [API_REFERENCE.md](API_REFERENCE.md) — contracts; keep in sync with frontend types and APIService.
- [CODE_STANDARDS.md](CODE_STANDARDS.md) — style guidance.

## Quick Commands
- Full stack start: `./start-dev.sh`
- Full stack stop: `./stop-dev.sh`
- Backend tests (prefer script): `./run-tests.sh backend`
- Frontend tests (require backend running, e.g., `./start-dev.sh`): `./run-tests.sh frontend`

## Terminal Usage Best Practices
**IMPORTANT: Reuse terminal sessions to avoid spawning excessive zsh processes.**

When running terminal commands:
- **DO NOT** create a new terminal session for every command
- **DO** chain related commands with `&&` when they're sequential
- **DO** use absolute paths in commands to avoid navigation issues
- **DO** run commands in the same working directory when possible

Bad pattern (creates many terminals):
```
# Command 1
# Command 2 in new terminal
# Command 3 in new terminal
```

Good pattern (reuses terminal):
```
cd /path/to/project && command1 && command2 && command3
```

For long-running processes (servers):
- Use `isBackground=true` parameter
- Check process status before starting another instance
- Use `./start-dev.sh` and `./stop-dev.sh` scripts instead of manual server commands

## Anti-Patterns to Avoid
- **Using mocks in tests**: Tests should use real API calls to the backend, not mocked responses.
- **Direct database operations in test bodies**: Use API calls for all test operations; fixtures may use direct DB access for setup only.
- Direct Supabase client use when `database_adapter.py` handles envs.
