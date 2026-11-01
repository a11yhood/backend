# a11yhood Documentation

All markdown documentation (except repository READMEs) lives here. Below is an index of what each file is for.

## Starter Guides
- [QUICK_START.md](QUICK_START.md) — One-command startup, URLs, seeded users, quick troubleshooting
- [LOCAL_TESTING.md](LOCAL_TESTING.md) — Full local setup, env vars, test data seeding, common tasks
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — End-to-end development workflow
- [PRD.md](PRD.md) — Product requirements
- [AGENT_GUIDE.md](AGENT_GUIDE.md) — What an agent should read and the helper conventions to follow

## Architecture & Data
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and component boundaries
- [API_REFERENCE.md](API_REFERENCE.md) — Backend endpoints
- [DATABASE.md](DATABASE.md) & [DATA_PERSISTENCE.md](DATA_PERSISTENCE.md) — Schema and storage approach
- [SOURCE_RATINGS.md](SOURCE_RATINGS.md) — Source rating logic

## Collections
- [COLLECTIONS_QUICK_REFERENCE.md](COLLECTIONS_QUICK_REFERENCE.md) — Quick reference for collections feature
- [COLLECTIONS_IMPLEMENTATION.md](COLLECTIONS_IMPLEMENTATION.md) — Detailed implementation notes
- [COLLECTIONS_COMPLETION_SUMMARY.md](COLLECTIONS_COMPLETION_SUMMARY.md) — Feature completion summary

## Testing & Quality
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md) — Overall QA approach
- [TEST_COVERAGE_MATRIX.md](TEST_COVERAGE_MATRIX.md) — Feature → test mapping (keep for role/test matrix reference)
- [USER_STORIES_AND_TESTS.md](USER_STORIES_AND_TESTS.md) — User stories with expected outcomes and linked tests
- [TESTS_UPDATED_SUMMARY.md](TESTS_UPDATED_SUMMARY.md) — Latest test updates for product submission flows
- [QA_IMPLEMENTATION_SUMMARY.md](QA_IMPLEMENTATION_SUMMARY.md) — QA assets created and why
- [TEST_README.md](TEST_README.md) — Frontend testing guide
- [ACCESSIBILITY_TESTING.md](ACCESSIBILITY_TESTING.md) — A11y testing procedures
- [OWNERSHIP_TESTS.md](OWNERSHIP_TESTS.md) — Product management testing notes
- [INTEGRATION_TESTS.md](INTEGRATION_TESTS.md) — Backend integration test setup and commands
- [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) — Fast test command reference

## Deployment
- [DEPLOYMENT_CURRENT.md](DEPLOYMENT_CURRENT.md) — **Current production deployment setup** (GitHub Actions, branch strategy, server config)
- [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) — Original deployment plan (historical reference)
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) — Pre-deployment verification checklist

## Standards, Security, Integrations
- [CODE_STANDARDS.md](CODE_STANDARDS.md) — Coding standards
- [SECURITY.md](SECURITY.md) — Security practices
- [OAUTH_SETUP.md](OAUTH_SETUP.md), [GITHUB_AUTH_SETUP.md](GITHUB_AUTH_SETUP.md), [RAVELRY_SETUP.md](RAVELRY_SETUP.md), [THINGIVERSE_SETUP.md](THINGIVERSE_SETUP.md) — Auth and scraper setup

## Audits & Reports
- [API_MISMATCH_AUDIT.md](API_MISMATCH_AUDIT.md) — Frontend/backend endpoint audit (now resolved)
- [LEGACY_CODE_AUDIT.md](LEGACY_CODE_AUDIT.md) — Legacy frontend code to remove
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) — Local testing implementation notes

Notes: The outdated `NAMING_CONVENTIONS.md` was removed; field naming is covered in current API contracts and tests.
