# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses tag-based [Semantic Versioning](https://semver.org/) (see
`README.md`'s "Developer Release Workflow" for how app (`vX.Y.Z`) and DB
(`db-vX.Y.Z`) tags are cut).

This file starts from the change below; prior history is not backfilled.

## [Unreleased]

### Added

- **`CORS_ORIGIN_REGEX` setting.** Optional regex (matched against the whole origin) that is allowed in addition to the exact `CORS_ORIGINS` list, so every Vercel preview deployment of the frontend (whose hostname changes per deploy) can call the test backend. Unset by default; leave it unset in production. An invalid pattern is logged and ignored.

### Changed

- **Faster blog post list.** `GET /api/blog-posts` now resolves header-image metadata for a page of posts in one batched query instead of one per post. It shares `resolve_image_metadata_batch` with the product list, which replaces the earlier alt-text-only helper. A failed batch lookup still degrades to "no image" but is now logged as a warning.
- **Faster `GET /api/products` (product list paging, frontend issue #441).** Image alt text for a page of products is now fetched in one query instead of one per product. The editor, tag and image-alt lookups for a page run concurrently rather than one after another. The canonical source names are served from a short-lived in-process cache (60 s TTL) instead of being re-read from `supported_sources` on every request; the cache is cleared when a source is created, updated, deleted or approved from a request, and after `/api/dev/reset`. Response shape is unchanged. Each worker/instance keeps its own cache, so a change made directly in the database (outside the API) can take up to a minute to show up.
- **Collection write endpoints now require the collection's/product's UUID `id`, not a slug** (issue #197). `PUT /api/collections/{id}`, `DELETE /api/collections/{id}`, add/remove editor, and add/remove product (single and bulk) all reject a slug with `404`. A collection's slug is regenerated whenever its name changes, so a stale slug can be reassigned to a different collection — accepting it on a write risked silently retargeting the wrong resource. Reads (`GET`) are unaffected and still accept either a slug or a UUID id.
- Documented the read-vs-write identifier contract explicitly in `documentation/API_REFERENCE.md`, including a deprecation notice: `product_ids` in collection responses is deprecated for building external-client routes/links (prefer `product_slugs`), though it remains the correct value for writes. Nothing is removed yet — see [#287](https://github.com/a11yhood/backend/issues/287), which tracks eventual `product_ids` removal.

### Added

- Tests for the supported-sources cache (cache hit, invalidation, TTL expiry, failed reads never cached, callers can't mutate the cached list) and for the batched image-alt lookup.
- Regression tests confirming `product_slugs` stays index-aligned with `product_ids`, including when a slug can't be resolved (`None` in place, not dropped or reordered).
- Regression tests confirming every collection write endpoint rejects a slug identifier.

### Removed

- **All Docker and GitLab CI tooling.** Production is deployed to Vercel only, and Vercel builds PRs through its own GitHub integration, so these are gone: the `Build and Push Docker Image` workflow (`.github/workflows/docker-build.yml`, which also published to `ghcr.io/a11yhood/backend` on `v*` tags), the `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.gitlab-ci.yml`, the `start-dev.sh`, `start-prod.sh` and `test-prod-image.sh` scripts (and their shared `scripts/lib/backend-common.sh`), and the `dev-seed`, `dev-reset`, `dev-stop`, `prod`, `prod-stop` and `test-prod-image` pixi tasks. The Docker setup docs (`DOCKER_SETUP.md`, `README.Docker.md`, `GITHUB_TO_GITLAB_CI_DEPLOY.md`) are removed and the README, `PIXI_TASKS.md`, `LOCAL_TESTING.md`, `seed_scripts/README.md` and release checklist are updated.

### Changed (local development)

- `pixi run dev` now runs the backend locally with uvicorn (auto-reload, HTTPS on `https://localhost:8443`, `.env.test`) instead of starting a Docker container on port 8002. `scripts/seed.sh` no longer has a Docker mode (`--in-docker` is gone); `pixi run seed` runs the seeds with the local Python venv. `scripts/db-export/verify_restore_local.sh` still uses a throwaway Postgres container to verify database exports.
