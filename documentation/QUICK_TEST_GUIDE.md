# Quick Test Guide

Fast reference for running tests and adding new tests in this repository.

## Which Test Layer?

1. Unit test
- Use for pure logic and adapters.
- Mark with `pytest.mark.unit`.
- No real DB calls.

2. Integration test (default backend layer)
- Use for API behavior and DB side effects.
- Mark with `pytest.mark.integration`.
- Use `client`, `auth_client`, `admin_client`, `clean_database` fixtures.

3. Live/system test
- Use only for external services or running backend validation.
- Mark as integration and gate with env vars.

## Common Commands

```bash
# Unit only
pixi run test-unit

# Integration only
pixi run test-integration

# Two-phase full suite
pixi run test

# Reset DB then run suite in one process chain
pixi run test-fresh

# Reset DB then run unit + integration in separate processes
pixi run test-fresh-split

# Single file
pixi run pytest tests/test_images_integration.py -q

# Single test
pixi run pytest tests/test_images_integration.py::test_image_upload_admin_success -q
```

## Add a New Test Checklist

1. Pick the right file and marker
- Unit: `tests/test_*.py` with `pytestmark = pytest.mark.unit`
- Integration: `tests/test_*.py` with `pytestmark = pytest.mark.integration`

2. Use project fixtures
- Prefer `client`, `auth_headers`, `test_user`, `test_admin`, `clean_database` for integration tests.
- Keep test setup deterministic (fixed slugs/ids where practical).

3. Assert behavior through API responses
- Prefer request/response assertions for route behavior.
- Use direct DB checks only when verifying persistence side effects that API does not expose directly.

4. Run the narrowest command first
- File-level test run, then broader suite if needed.

5. Update docs if contract/behavior changed
- `documentation/API_REFERENCE.md` for API changes.
- `documentation/TEST_COVERAGE_MATRIX.md` and story docs when coverage scope changes.

## CI Coverage (Current)

PR CI runs:
- unit tests: `pixi run pytest -m unit -q`
- integration smoke set: `tests/test_main.py tests/test_auth_fixture_determinism.py tests/test_timestamp_serialization.py`

PR CI does not run the full integration suite by default.

## Should CI use test-fresh?

Default PR CI should generally stay on smoke + unit for runtime and external DB reliability.

Recommended pattern:
- Keep PR CI fast (unit + smoke).
- Run `pixi run test-fresh-split` in a scheduled/nightly workflow and/or manual dispatch for deeper coverage.
