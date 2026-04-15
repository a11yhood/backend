# Dev Mode Features & API

## Overview

Dev mode enables safe local development with:
- **Dual dev-token auth** (UUID-based for deterministic tests, role-based for frontend/manual dev)
- **Automatic database row limits** (20 rows max per table — enforced on every insert)
- **Disabled scheduled scrapers** (test scrapers limited to 5 products)
- **Database reset endpoint** for cleanup
- **Dev statistics/monitoring** endpoints

Enabled when `TEST_MODE=true` in `.env.test`.

---

## Authentication

### Two Token Formats

Dev mode supports two `Authorization: Bearer` token formats.  Choose the right one for your use case:

| Format | When to Use | Example |
|--------|-------------|---------|
| `dev-token-<uuid>` | **Deterministic tests** — maps to the exact seeded user row | `Bearer dev-token-2a3b7c3e-971b-4b42-9c8c-0f1843486c50` |
| `dev-token-<role>` | **Role-behaviour tests / frontend dev** — creates/fetches a shared `dev_<role>` user | `Bearer dev-token-admin` |
| `X-Dev-Role: <role>` | **Frontend dev only** — same as role token but via header | `X-Dev-Role: moderator` |

**Parse order** (backend evaluates in this order):
1. `X-Dev-Role` header → role-based, create-on-demand
2. `Bearer dev-token-<uuid>` → look up exact user by ID (404 if missing)
3. `Bearer dev-token-<role>` → role-based, create-on-demand

All dev tokens require `TEST_MODE=true`; they are silently ignored (401) in production.

### UUID Tokens (for Tests)

```bash
# Authenticate as the exact seeded regular user
curl -H "Authorization: Bearer dev-token-2a3b7c3e-971b-4b42-9c8c-0f1843486c50" \
  http://localhost:8002/api/users/me
```

Seeded test UUIDs (defined in `tests/test_data.py` and `services/auth.py`):

| UUID | Username | Role |
|------|----------|------|
| `49366adb-2d13-412f-9ae5-4c35dbffab10` | `admin_user` | admin |
| `94e116f7-885d-4d32-87ae-697c5dc09b9e` | `moderator_user` | moderator |
| `2a3b7c3e-971b-4b42-9c8c-0f1843486c50` | `regular_user` | user |

### Role Tokens (for Frontend / Role-Behaviour Tests)

```bash
# Test as admin
curl -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/users/me

# Test as moderator
curl -H "X-Dev-Role: moderator" http://localhost:8002/api/products

# Test as regular user
curl -H "Authorization: Bearer dev-token-user" http://localhost:8002/api/products
```

Valid roles: `admin`, `moderator`, `manager`, `user`

### Frontend Implementation Example

```javascript
// Use X-Dev-Role for role switching in manual frontend dev
async function callApi(role = "user") {
  const response = await fetch("http://localhost:8002/api/products", {
    headers: { "X-Dev-Role": role },
  });
  return response.json();
}
```

---

## Database Row Limits

**Automatic enforcement** on every insert in TEST_MODE: inserting into a table that already holds ≥ 20 rows raises a `ValueError` before the row reaches the database.  This prevents accidental mass-inserts from filling your test instance.

### Configuration

```python
# config.py
DEV_MODE_MAX_ROWS_PER_TABLE: int = 20
```

### Limits Apply To

- `products`
- `users`
- `ratings`
- `discussions`
- `collections`
- `scraping_logs`
- `oauth_configs`

(System tables such as `supported_sources`, `scraper_search_terms`, and join tables are exempt.)

### When You Hit the Limit

1. Remove old test data manually
2. Use the reset endpoint (see below)
3. Query to verify counts: `GET /api/dev/stats`

---

## Disabled Scrapers

### Production Behavior
- GitHub: Daily at 2:00 AM UTC
- Thingiverse: Daily at 2:30 AM UTC
- Ravelry: Daily at 3:00 AM UTC

### Dev Behavior
- **All scheduled scrapers disabled** (controlled by `TEST_MODE`)
- Test scrapers limited to 5 products per run
- Can still trigger scraper manually via API:
  ```bash
  POST /api/scrapers/github/search \
    -H "Authorization: Bearer $DEV_TOKEN" \
    -d '{"term": "accessible"}'
  ```

### Configuration

```python
# config.py
TEST_SCRAPER_LIMIT: int = 5  # Max products per manual run
```

---

## Dev-Only API Endpoints

### GET `/api/dev/stats` (Admin Only)

View current dev configuration and table row counts.

```bash
curl -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/stats
```

Response:
```json
{
  "mode": "dev",
  "max_rows_per_table": 20,
  "test_scraper_limit": 5,
  "tables": {
    "products": {"rows": 15, "at_limit": false},
    "users": {"rows": 4, "at_limit": false},
    "ratings": {"rows": 8, "at_limit": false},
    ...
  }
}
```

### POST `/api/dev/reset` (Admin Only)

⚠️ **Dangerous**: Clears ALL data from user tables.

```bash
curl -X POST -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/reset
```

Response:
```json
{
  "status": "reset",
  "cleared_tables": {
    "products": 15,
    "users": 4,
    "ratings": 8,
    ...
  },
  "total_rows_deleted": 125
}
```

After reset:
1. Database is empty
2. Reseed with test data if needed: `pixi run dev-seed`

### GET `/api/dev/check-limits` (Admin Only)

Manually check if any table exceeds row limit.

```bash
curl -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/check-limits
```

Returns **200** if all within limits, **400** if any table exceeds:
```json
{
  "detail": "Dev row limits exceeded (max 20):\n  - products: 45/20\n  - ratings: 32/20"
}
```

### GET `/api/dev/health-dev` (No Auth Required)

Confirm dev endpoints are available.

```bash
curl http://localhost:8002/api/dev/health-dev
```

Response:
```json
{
  "status": "healthy",
  "mode": "dev",
  "message": "Dev mode active - endpoints available"
}
```

---

## Security

### Production
- Dev tokens / X-Dev-Role header **ignored** (401)
- Dev endpoints **not mounted** (404)
- All schedulers **enabled**
- Row limits **inactive**

### Dev Mode
- UUID dev tokens resolve to exact seeded user rows
- Role tokens / X-Dev-Role create test users on demand (username: `dev_<role>`)
- Dev endpoints **require admin role**
- Schedulers **disabled** (reduces API load in TEST_MODE)
- Row limits **enforced on every insert**

---

## Workflow Example

### 1. Test All Roles

```bash
# Start backend in dev mode
pixi run dev-start

# Test admin features
curl -H "Authorization: Bearer dev-token-admin" ...

# Test moderator features
curl -H "X-Dev-Role: moderator" ...

# Test specific seeded user
curl -H "Authorization: Bearer dev-token-2a3b7c3e-971b-4b42-9c8c-0f1843486c50" ...
```

### 2. Check Your Test Data

```bash
curl -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/stats
```

### 3. Clean Up When Full

```bash
# View stats
curl -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/stats

# If you hit limits:
curl -X POST -H "Authorization: Bearer dev-token-admin" http://localhost:8002/api/dev/reset

# Reseed
pixi run dev-seed
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Dev tokens only in TEST_MODE" | Running with `.env` (production) | Use `.env.test` or set `TEST_MODE=true` |
| "Invalid dev token role 'foo'" | Wrong role name | Use: `admin`, `moderator`, `manager`, or `user` |
| "Dev user not found: \<uuid\>" | UUID not in DB | Run `pixi run dev-seed` to reseed test users |
| "Dev row limits exceeded" | Too much test data | `POST /api/dev/reset` then `pixi run dev-seed` |
| Dev endpoints return 404 | Not in dev mode | Confirm `TEST_MODE=true` in `.env.test` |

