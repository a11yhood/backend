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

Recommended naming for this repo:

- `origin` -> `git@github.com:a11yhood/backend.git` (primary remote)
- `gitlab` -> `git@gitlab.cs.washington.edu:a11yhood/backend.git` (deployment remote)

Why this is recommended:

- Most tools (including Magit defaults) assume `origin` exists.
- GitHub remains the source of truth.
- GitLab pushes stay explicit and predictable.

Set up or normalize remotes:

```bash
# Ensure origin points to GitHub
git remote set-url origin git@github.com:a11yhood/backend.git

# Add gitlab once (ignore if it already exists)
git remote add gitlab git@gitlab.cs.washington.edu:a11yhood/backend.git

# Branch defaults for CLI + Magit
git config branch.main.remote origin
git config branch.main.merge refs/heads/main
git config remote.pushDefault origin

git remote -v
```

If you are not using GitLab pull mirroring, push to GitLab explicitly:

```bash
git push gitlab main
git push gitlab --tags
```

## Magit + CLI Working Model

Use one simple rule: push branches/PR work to `origin`, then sync `main` and tags to `gitlab` after merge.

- Day-to-day branch pushes: default to `origin`.
- Post-merge deployment sync: explicitly push `main` and tags to `gitlab`.

Equivalent CLI commands:

```bash
# feature branch / PR flow
git push origin <feature-branch>

# after PR merge to main
git checkout main
git pull origin main
git push gitlab main
```

In Magit, this stays easy because `remote.pushDefault=origin` keeps the default push target as GitHub while still allowing one-off pushes to `gitlab` from the push popup.

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

## Suggested Release Flow

1. Merge reviewed work into `main` on GitHub.
2. Sync local `main` from GitHub.
3. Push `main` to GitLab (`git push gitlab main`) and confirm `deploy_test` succeeds.
4. Create an annotated release tag from `main`.
5. Push the tag to both remotes.
6. Open the GitLab tag pipeline and manually trigger `deploy_prod`.

Example:

```bash
git checkout main
git pull origin main

git push gitlab main

git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
git push gitlab vX.Y.Z
```

### Updating a Tag (Before and After Push)

Only move tags when necessary (for example, wrong commit or wrong version contents).

Before the tag is pushed anywhere:

```bash
git tag -d vX.Y.Z
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

After the tag was already pushed:

```bash
# Recreate locally at the correct commit (run from desired commit)
git tag -fa vX.Y.Z -m "Release vX.Y.Z"

# Replace on GitHub
git push origin :refs/tags/vX.Y.Z
git push origin vX.Y.Z

# Replace on GitLab
git push gitlab :refs/tags/vX.Y.Z
git push gitlab vX.Y.Z
```

If tag protection blocks delete/recreate, use a new tag instead (for example `vX.Y.Z+fix1` or `vX.Y.(Z+1)`).

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
