# Manual Migrations

This directory is for one-off SQL fixes that should be run manually in a specific environment and should not be auto-applied by the normal migration runner.

Use this for:
- emergency production fixes
- environment-specific patches
- rollback or repair scripts
- temporary operational SQL that should not replay on fresh installs

Rules:
- Keep files idempotent when possible.
- Never assume files here will be applied by `scripts/apply-migrations.sh`.
- Document the target environment and run order in the file header.
- Move a file here only after you no longer want it in the canonical replayable migration chain.

Notes:
- Canonical schema history still belongs in `migrations/`.
- Test-only helpers still belong in `migrations/test_only/`.

## Current Manual Migrations

### 20260508_hotfix_images_payload_and_dedupe.sql
- **Applied**: 2026-05-09 (production)
- **Purpose**: Repair images table data after schema divergence
  - Separates data URLs from canonical_url column (fix for PostgreSQL error 54000: index row too large)
  - Dedupes images by canonical_key using DISTINCT ON
  - Repairs product/blog post image_id FK references
- **Why manual**: One-time data repair for a specific production state. New environments get clean schema from `20260508_add_images_table_and_references.sql`
- **Production status**: Applied and recorded in schema_migrations
- **Future**: Can delete after all environments are consistent with deduplicated schema
