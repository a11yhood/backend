# Database Export Scripts

Tools for exporting a11yhood database in different formats for different use cases.

## Overview

| Export Type | File | Command | Use Case | Public? |
|---|---|---|---|---|
| **Public Products** | `public-products.sql` | `pixi run export-public` | Share curated dataset with researchers | ✅ Yes |
| **Private Full** | `full-database.sql` | `pixi run export-private` | Organizational backup, internal testing | ❌ Private |

## Scripts

### 1. `export_full_database.py --mode public` 
Exports products + aggregated ratings + tags (no user data).

**Includes:**
- `products` → public columns only (name, description, image, source_rating, etc.)
- `product_urls` → publicly accessible links
- `product_tags` + `tags` → product categorization
- `ratings` → aggregated into `products.computed_rating` (avg per product, no user IDs)
- `supported_sources` + `valid_categories` → reference data

**Excludes:**
- User names, emails, IDs, bio, location
- Product metadata (external_id, scraped_at, editor details)
- Banned product status
- Private OAuth tokens

**Usage:**
```bash
pixi run export-public
# or
python scripts/db-export/export_full_database.py --mode public --output supabase/public-products.sql --env-file .env
```

**Output:** `supabase/public-products.sql` (size depends on production dataset)

**Source environment:** Production (`.env`) by default. The exporter paginates through the full public dataset, so large tables are not truncated at the first API page.

---

### 2. `export_full_database.py --mode private`
Full database dump including all tables and all data.

**Includes:** All tables, all columns, all data — including:
- `users` (emails, profiles)
- `oauth_configs` (authentication configs)
- `scraping_logs` (internal scraper logs)
- All product, rating, and collection data

**Excludes:** Nothing — this is a complete backup intended for authorized team use only.

**Usage:**
```bash
pixi run export-private
# or
python scripts/db-export/export_full_database.py --mode private --output supabase/full-database.sql --env-file .env
```

**⚠️ SECURITY:**
- Contains user emails, OAuth configs (test), private collections
- **Never commit to public repositories**
- Add to `.gitignore`
- Restrict to authorized team members

**Output:** `supabase/full-database.sql` (size varies, typically 1-10MB)

---

## Workflow: Local Testing

### Export locally and test:

```bash
# 1. Export public products
pixi run export-public
ls -lh supabase/public-products.sql

# 2. Export private (for backup)
pixi run export-private
ls -lh supabase/full-database.sql

# 4. Validate schema, privacy rules, and live row counts
pixi run validate-exports
```

### Restore exported data:

```bash
# Restore test database to local Supabase
supabase db push < supabase/data.sql
```

---

## Operational Backup (pg_dump)

Use this before destructive or high-risk production database changes (for example: schema hotfixes, large data migrations, one-time cleanup scripts).

### Recommended: pooler connection details from Supabase Dashboard

1. In Supabase, open the project and copy connection details from **Shared Pooler** (or the pooler variant that works on your network).
2. Export connection values as libpq environment variables:

```bash
export PGHOST='aws-1-us-east-1.pooler.supabase.com'
export PGPORT='5432'
export PGDATABASE='postgres'
export PGUSER='postgres.<project-ref>'
export PGPASSWORD='YOUR_DB_PASSWORD'
export PGSSLMODE='require'
```

3. Verify connectivity:

```bash
psql -c "select 1;"
```

4. Create the backup:

```bash
mkdir -p backups
pg_dump --format=custom --file backups/prod-pre-hotfix.dump
```

5. (Optional) Validate the dump file exists and has non-zero size:

```bash
ls -lh backups/prod-pre-hotfix.dump
```

### Notes

- Prefer env vars over a single connection URI when troubleshooting host/credential parsing issues.
- If `pg_dump` shows host translation errors, verify you copied the exact host shown in Supabase connection settings.
- Dedicated poolers may require specific network compatibility; if resolution/connectivity fails, use the compatible shared/session pooler details from the dashboard.
- Keep dumps private. Do not commit files under `backups/` to git.

---

## GitHub Actions Integration

These scripts are designed to be called from `.github/workflows/db-release.yml`:

```yaml
- name: Export databases
  run: |
    pixi run export-public
    pixi run export-private
    
- name: Create Release
  uses: actions/create-release@v1
  with:
    files: |
      supabase/public-products.sql
    # supabase/full-database.sql -> Private release (restricted access)
```

---

## Details: What's Exported?

### Public Products Export
```
valid_categories      ✓ All data
supported_sources     ✓ All data
tags                  ✓ All data
products              ✓ Public columns only (14 of 25 fields)
product_urls          ✓ All data
product_tags          ✓ All data
ratings               ✓ Aggregated (avg, count per product, NO user IDs)
---
users                 ✗ Excluded
discussions           ✗ Excluded
collections           ✗ Excluded (private user data)
oauth_configs         ✗ Excluded
```

### Private Full Export
```
ALL TABLES            ✓ All data
oauth_configs         ~ Schema only (data excluded)
scraping_logs         ~ Schema only (data excluded)
```

---

## Best Practices

1. **Public Release**: Update monthly via GitHub Actions, automate via CI/CD
2. **Private Release**: Restricted access, GitHub Secret stored safely, audit logs enabled

### Validation checks

`pixi run validate-exports` verifies:
- Exported tables match the intended table set
- Public product export does not leak forbidden columns
- Exported columns conform to the baseline schema
- Exported row counts match the live source database for every exported table
- Public ratings metadata matches both aggregated product count and raw source rating count

### .gitignore
```gitignore
# Keep exported SQL files out of repo
supabase/public-products.sql
supabase/full-database.sql
```

### Security Checklist
- [ ] Never commit `.sql` files with real user data
- [ ] Private exports → restricted release visibility
- [ ] Personal data removed from public exports
- [ ] OAuth secrets excluded from all exports
- Scraper logs excluded from exports (internal only)

---

## Troubleshooting

**Can't export? Supabase CLI missing:**
```bash
npm install -g @supabase/cli
# or
pixi install -f db  # Install with db feature
```

**Database connection error?**
```bash
# Verify credentials
echo $SUPABASE_URL
echo $SUPABASE_KEY

# Check .env file
cat .env       # For production database
```

**Empty export?**  
Check that data exists in Supabase and your service role key has full permissions.

**Large file size?**  
You may need to:
- Exclude certain tables with `--exclude-table-data`
- Run `pixi run export-test` instead (smaller, test data only)
- Use compression: `gzip supabase/full-database.sql`

---

## See Also

- [Database Schema](../supabase-schema.sql)
- [Seed Scripts](../seed_scripts/)
- [Supabase CLI Docs](https://supabase.com/docs/guides/cli)
