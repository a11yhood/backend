# GitHub Repository + GitLab CI Deployment

This guide explains how this repository uses GitHub as the source of truth while GitLab CI performs validation, build, and deployment.

## Current Deployment Model

1. Code is developed and reviewed in GitHub.
2. Changes are mirrored (or pushed) to the GitLab remote.
3. GitLab pipeline runs from [.gitlab-ci.yml](../.gitlab-ci.yml).
4. Test deployment runs automatically from `main`.
5. Production deployment runs manually from tag pipelines.

Important: deployment jobs run on host-specific GitLab runners, not over SSH from a generic runner.

## Git Remote Setup

This repo is expected to have both remotes:

- `github`: `git@github.com:a11yhood/backend.git`
- `gitlab`: `git@gitlab.cs.washington.edu:a11yhood/backend.git`

Verify:

```bash
git remote -v
```

If you are not using GitLab pull mirroring, push branches and tags explicitly:

```bash
git push gitlab --all
git push gitlab --tags
```

## Required GitLab CI Variables

Set these variables in GitLab CI/CD settings:

- `ENV_TEST_FILE` (recommended type: File): `.env.test` content for test deployments.
- `ENV_PROD_FILE` (recommended type: File, protected): `.env` content for production deployments.

Notes:

- The pipeline copies these files during deploy jobs:
  - test: `cp "$ENV_TEST_FILE" .env.test`
  - prod: `cp "$ENV_PROD_FILE" .env`
- Do not commit deployment secrets to the repository.

## Pipeline Behavior

Configured in [.gitlab-ci.yml](../.gitlab-ci.yml):

- `validate:compose`
  - Runs on branches and tags.
  - Executes `docker compose config` to verify Compose syntax and interpolation.

- `build:image`
  - Runs on branches and tags.
  - Executes `docker build -t a11yhood-backend:$CI_COMMIT_SHORT_SHA .`.

- `deploy_test`
  - Runs only on `main`.
  - Uses runner tag `lab-docker-test`.
  - Copies test env file and executes `docker compose up -d --build`.
  - Publishes environment URL `https://a11yhood-test.cs.washington.edu`.

- `deploy_prod`
  - Runs only on tag pipelines.
  - Uses runner tag `lab-docker-prod`.
  - Is manual (`when: manual`) as the production approval gate.
  - Copies prod env file and executes `docker compose --profile production up -d --build`.
  - Publishes environment URL `https://a11yhood.cs.washington.edu`.

## Day-to-Day Development Workflow

All changes should flow through GitHub. Never commit the same fix separately on GitLab.

**Step 1 — Start from an up-to-date `main`:**

```bash
git checkout main
git fetch github gitlab
git rebase github/main
```

**Step 2 — Create a feature branch, do work, commit:**

```bash
git checkout -b your-feature-branch
# ... make changes ...
git add -p
git commit -m "your message"
```

**Step 3 — Push to GitHub and open a PR:**

```bash
git push github your-feature-branch
# Open a PR on GitHub and merge it through normal review.
```

**Step 4 — After the PR merges, sync local `main` from GitHub:**

```bash
git checkout main
git fetch github
git rebase github/main
```

**Step 5 — Propagate to GitLab to trigger CI:**

```bash
git push gitlab main
```

This triggers the `deploy_test` job on GitLab automatically.

**Edge case — moving already-existing commits to a branch:**

If you find yourself needing to move commits that were applied to `main` directly (e.g. during the setup session that created this document), cherry-pick only those specific commits onto the correct feature branch rather than committing the same changes again:

```bash
git checkout your-feature-branch
git cherry-pick <commit-sha> [<commit-sha> ...]
git push gitlab your-feature-branch
```

## Suggested Release Flow

1. Merge reviewed work into `main` on GitHub.
2. Ensure `main` is available in GitLab (mirror or `git push gitlab main`).
3. Confirm `deploy_test` succeeds in GitLab.
4. Create and push a release tag, for example `vX.Y.Z`.
5. Open the GitLab tag pipeline and manually trigger `deploy_prod`.

## Local Verification Before CI

Run local checks before relying on CI:

```bash
# quick compose validation
docker compose config > /dev/null

# optional local image build parity check
docker build -t a11yhood-backend:local .
```

For backend behavior checks, prefer the local test workflow:

```bash
pixi run test-unit
pixi run test-integration
```

## Security Notes

- Store secrets in GitLab CI variables and environment files, not in git.
- Keep `ENV_PROD_FILE` protected and restricted to protected refs.
- Keep `deploy_prod` as a manual action with limited approver access.
