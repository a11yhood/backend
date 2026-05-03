# GitHub Process and Protection Checklist

Use this as a working checklist for repository governance and release flow.

## How to Use This Checklist

Not everything below is a `main` branch protection toggle.

- `Branch protection (main ruleset)` = enforced gate before merge to `main`.
- `Tag protection` = enforced gate for creating release tags.
- `Actions security / environments` = repository-wide controls.
- `PR workflow` = team behavior and CI runs; not all of it is a branch ruleset checkbox.

### Quick Answer: Should main branch protection include everything?

No. Put only merge-gating controls in the `main` branch ruleset. Keep tag controls in tag rulesets, and keep release-process actions in team workflow docs.

### What Goes Where

#### Main branch ruleset (`main` only)

- Require pull request before merge
- Require approvals
- Dismiss stale approvals
- Require conversation resolution
- Require status checks (`Build and Push Docker Image / build`, `CI / lint`, `CI / test`)
- Require branch up to date before merge
- Disable force pushes
- Disable branch deletion

#### Tag rulesets (`v*`, `db-v*`)

- Restrict who can create/update/delete matching tags

#### Actions / environments (repo settings)

- Default `GITHUB_TOKEN` permissions
- Allowed actions policy
- Fork PR workflow approval policy
- Optional environment reviewers for publish jobs

#### PR process (team behavior)

- Open PR, pass checks, get reviews, merge
- Cut tags from up-to-date `main`

## A) Confirm Current Workflow Behavior

- [x] Open GitHub Actions and inspect latest **Build and Push Docker Image** run.
- [ ] Confirm event/ref is expected (`pull_request`, `push` tag, or `workflow_dispatch`).
- [ ] Open latest **Export and Release Databases** run.
- [ ] Confirm event/ref is expected (`push` on `db-v*` tag or `workflow_dispatch`).
- [ ] Verify workflow files in repo:
  - [ ] `.github/workflows/docker-build.yml`
  - [ ] `.github/workflows/db-release.yml`

## B) One-Time Repository Protections (Admin)

### Branch Protection for `main`

Apply these in **Settings -> Rules -> Rulesets -> Branch ruleset (target: main)**.

- [x] Create/verify branch ruleset for `main`.
- [x] Require pull request before merge.
- [x] Require at least 1 approval (or your team standard).
- [x] Dismiss stale approvals on new commits.
- [x] Require conversation resolution before merge.
- [x] Require status checks to pass.
- [x] Require branch to be up to date before merge.
- [x] Disable force pushes.
- [x] Disable branch deletion.

Recommended optional toggles (decide as a team):

- [ ] Require CODEOWNERS review for matching paths.
- [ ] Restrict who can push to matching branches.
- [ ] Disable admin bypass for protected branch rules.

### Required Checks

These are selected inside the `Require status checks to pass` part of the `main` branch ruleset.

- [x] Run at least one PR so check names appear.
- [x] Add required check: `Build and Push Docker Image / build`.
- [x] Add required check: `CI / lint`.
- [x] Add required check: `CI / test`.

Do not add as required checks for `main`:

- [ ] `Export and Release Databases` (tag/manual workflow, not PR gate).
- [ ] Dependabot maintenance runs that are not your PR quality gates.

### Tag Protection (Publish Control)

Apply these in **Settings -> Rules -> Rulesets -> Tag ruleset** (not branch rulesets).

- [x] Add tag ruleset for `v*`.
- [x] Restrict create/update/delete on `v*` to maintainers.
- [ ] Add tag ruleset for `db-v*`.
- [ ] Restrict create/update/delete on `db-v*` to maintainers.

### Actions Security

Apply these in **Settings -> Actions -> General**.

- [x] Set default `GITHUB_TOKEN` permissions to least privilege (read-only where possible).
- [ ] Restrict allowed actions to trusted/verified actions.
- [x] Require approval for workflow runs from fork PRs.

### Optional Approval Gates

Apply these in **Settings -> Environments**.

- [x] Create environment `production-image`.
- [ ] Create environment `production-db-export`.
- [x] Add required reviewers for these environments.
- [ ] Wire publish jobs to these environments.

Current workflow mapping:

- [x] `.github/workflows/docker-build.yml` -> `jobs.publish.environment: production-image`
- [x] `.github/workflows/db-release.yml` -> `jobs.export.environment.name: production-db-export`
- [x] Keep `.github/workflows/docker-build.yml` `jobs.build` (PR validation) without an environment.

## C) Ongoing Developer Release Workflow

### Every Change

- [ ] Open PR to `main`.
- [ ] Ensure CI checks pass.
- [ ] Get required review(s).
- [ ] Merge PR.

### Publish Docker Image (when needed)

- [ ] Sync local `main` (`git checkout main && git pull`).
- [ ] Create app release tag (`X.Y.Z`).
- [ ] Push tag to GitHub (`git push origin vX.Y.Z`).
- [ ] Push tag to GitLab (`git push gitlab vX.Y.Z`).
- [ ] Confirm Docker publish workflow succeeded in Actions.
- [ ] Confirm GitLab tag pipeline sees `vX.Y.Z`.

### Publish Database Export Release (when needed)

- [ ] Sync local `main` (`git checkout main && git pull`).
- [ ] Create DB release tag (`git tag db-vX.Y.Z`).
- [ ] Push tag to GitHub (`git push origin db-vX.Y.Z`).
- [ ] Push tag to GitLab (`git push gitlab db-vX.Y.Z`).
- [ ] Confirm DB export workflow succeeded in Actions.

## D) Quick Sanity Checks After Any Release

- [ ] Confirm expected image tags exist in GHCR.
- [ ] Confirm expected GitHub release assets were created (for DB exports).
- [ ] Document release/tag in team notes or changelog.
