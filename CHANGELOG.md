# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses tag-based [Semantic Versioning](https://semver.org/) (see
`README.md`'s "Developer Release Workflow" for how app (`vX.Y.Z`) and DB
(`db-vX.Y.Z`) tags are cut).

This file starts from the change below; prior history is not backfilled.

## [Unreleased]

### Changed

- **Collection write endpoints now require the collection's/product's UUID `id`, not a slug** (issue #197). `PUT /api/collections/{id}`, `DELETE /api/collections/{id}`, add/remove editor, and add/remove product (single and bulk) all reject a slug with `404`. A collection's slug is regenerated whenever its name changes, so a stale slug can be reassigned to a different collection — accepting it on a write risked silently retargeting the wrong resource. Reads (`GET`) are unaffected and still accept either a slug or a UUID id.
- Documented the read-vs-write identifier contract explicitly in `documentation/API_REFERENCE.md`, including a deprecation notice: `product_ids` in collection responses is deprecated for building external-client routes/links (prefer `product_slugs`), though it remains the correct value for writes. Nothing is removed yet — see [#287](https://github.com/a11yhood/backend/issues/287), which tracks eventual `product_ids` removal.

### Added

- Regression tests confirming `product_slugs` stays index-aligned with `product_ids`, including when a slug can't be resolved (`None` in place, not dropped or reordered).
- Regression tests confirming every collection write endpoint rejects a slug identifier.
