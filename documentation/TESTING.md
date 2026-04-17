# Testing Guide

This project uses three test layers. Use the lightest layer that can prove the behavior.

## 1) Unit Tests

Use for pure logic with no real DB, no FastAPI app startup, and no network calls.

- Scope: helper functions, parsing, normalization, policy predicates, small adapters
- Speed: fast
- Marker: `@pytest.mark.unit` (or module-level `pytestmark = pytest.mark.unit`)
- Default tools:
  - `monkeypatch` for env vars and symbol replacement
  - plain asserts on returned values/errors

Examples to keep in this layer:
- dev token parsing
- startup security predicates
- slug/normalization helpers
- row-limit helper behavior with stub clients

## 2) Integration Tests (default backend layer)

Use for in-process API behavior against the Supabase test DB.

- Scope: route behavior, auth/authorization, DB side effects, workflow paths
- Stack:
  - FastAPI `TestClient`
  - DB dependency override to test Supabase
  - per-test cleanup and reseed via `tests/conftest.py`
- Marker: `pytest.mark.integration`
- These are not unit tests; they are API integration tests with real persistence.

Typical files in this layer:
- endpoint suites under `tests/test_*.py` that use `client`, `auth_client`, `admin_client`, `clean_database`, `test_user`, etc.

## 3) Live/System Tests

Use only when validating against a running backend or real external services.

- Scope: scraper integrations, real API calls, end-to-end behavior outside TestClient
- Marker: `pytest.mark.integration` plus `pytest.mark.slow` and/or other specific markers
- Must be opt-in (env-gated) and safe to skip by default.

Current examples:
- `tests/test_scrapers_integration.py`
- `tests/test_scrapers_live_api.py`

## Choosing a layer

1. If no DB/app/network is required, write a unit test.
2. If behavior depends on route wiring or DB state, write an integration test.
3. If behavior depends on external systems or a running server, write a live/system test.

## Mocking Style Rules

Prefer one style per file unless there is a clear reason to mix.

Use `monkeypatch` when:
- setting environment variables (`monkeypatch.setenv`)
- replacing module functions/attributes directly
- patching simple collaborators in pytest-native style

Use `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) when:
- call inspection/assertion is required
- chained/object-like mocks are clearer than ad hoc stubs
- async call behavior or rich mock features are needed

Avoid local ad hoc fake classes unless they significantly improve readability.

## Auth Fixture Guidance

Backend tests should prefer deterministic UUID-based dev auth for identity-sensitive checks.

- Identity-sensitive assertions (owner checks, `/api/users/me`) should use seeded-user UUID tokens.
- Role-only behavior tests may use role-based dev tokens.
- Keep frontend/manual dev flows role-token-friendly, but keep backend tests deterministic.

## Marker usage and commands

Run only unit tests:

```bash
pixi run test-unit
```

Run integration tests:

```bash
pixi run test-integration
```

Run the full suite as two phases:

```bash
pixi run test
```

Skip slow tests:

```bash
pixi run pytest -m "not slow"
```

Run live scrapers explicitly:

```bash
RUN_LIVE_SCRAPERS=1 RUN_AGAINST_SERVER=1 BACKEND_BASE_URL=http://localhost:8000 pixi run pytest tests/test_scrapers_live_api.py -v
```

## Performance note

The test harness now supports a fast cleanup path via `truncate_test_tables()` RPC.
Apply this SQL once to the test Supabase instance:

- `migrations/test_only/20260414_add_truncate_test_tables_rpc.sql`

The dev reset endpoint supports a separate fast reset path via `dev_truncate_all_tables()`.
Apply this SQL once to the test Supabase instance as well:

- `migrations/test_only/20260415_dev_truncate_all_tables.sql`

Without that RPC, cleanup falls back to slower per-table deletes.
