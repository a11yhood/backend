# GitHub Repository + GitLab CI Deployment

This guide explains how to keep source code in GitHub while deploying to department test and production hosts with GitLab CI.

## How It Works

1. GitHub remains the source of truth for code, pull requests, and releases.
2. GitLab CI runs pipelines when branch/tag updates arrive.
3. Deploy jobs SSH to test/prod hosts and run Docker Compose there.
4. Test deploys from `main` automatically.
5. Production deploys from release tags manually (approval gate).

## One-Time Setup

### 1. Connect GitHub to GitLab

Use one of these options:

- Pull mirror in GitLab (recommended).
- GitLab project that pulls from GitHub with deploy token.

For either option, confirm GitLab receives:

- `main` updates.
- Release tags like `v1.2.3`.

### 2. Add CI Variables In GitLab

Set the following as masked/protected variables:

- `TEST_DEPLOY_SSH_PRIVATE_KEY`: private key used by CI to SSH to the test host.
- `PROD_DEPLOY_SSH_PRIVATE_KEY`: private key used by CI to SSH to the production host.
- `GITHUB_REPO_URL`: repository clone URL reachable by target hosts.
  - Example (SSH): `git@github.com:a11yhood/backend.git`
  - Example (HTTPS token): `https://<token>@github.com/a11yhood/backend.git`
- `TEST_DEPLOY_HOST`: hostname/IP of test server.
- `TEST_DEPLOY_USER`: SSH user for test server.
- `TEST_DEPLOY_PORT`: SSH port for test server (optional, defaults to 22).
- `PROD_DEPLOY_HOST`: hostname/IP of production server.
- `PROD_DEPLOY_USER`: SSH user for production server.
- `PROD_DEPLOY_PORT`: SSH port for production server (optional, defaults to 22).

### 3. Prepare Test Host

Run once on the test host:

```bash
sudo mkdir -p /opt/a11yhood/backend-test
sudo chown -R <deploy-user>:<deploy-user> /opt/a11yhood/backend-test
```

Requirements on host:

- Docker Engine installed.
- Docker Compose plugin available (`docker compose version`).
- Deploy user can run Docker commands.

### 4. Prepare Production Host

Run once on the production host:

```bash
sudo mkdir -p /opt/a11yhood/backend-prod
sudo chown -R <deploy-user>:<deploy-user> /opt/a11yhood/backend-prod
```

Requirements on host:

- Docker Engine installed.
- Docker Compose plugin available (`docker compose version`).
- Deploy user can run Docker commands.
- Production `.env` created at `/opt/a11yhood/backend-prod/.env`.

## Pipeline Behavior

Configured in [.gitlab-ci.yml](../.gitlab-ci.yml):

- `validate:compose`: checks Compose renders cleanly.
- `build:image`: verifies Docker build succeeds.
- `deploy:test`: on `main`, SSH deploys `backend` service to test host.
- `deploy:prod`: on release tags `vX.Y.Z`, manual SSH deploys `backend-prod` with `production` profile.

## Local Prerequisite Check (Before Adopting CI)

Before relying on CI, verify local Compose behavior in this repo:

```bash
docker compose build backend
docker compose up -d backend
curl -k https://localhost:8000/health || curl http://localhost:8000/health
docker compose down
```

For production profile locally:

```bash
docker compose --profile production up -d --build backend-prod
curl http://localhost:8001/health
docker compose --profile production down
```

## Release Flow

1. Merge reviewed code into `main` on GitHub.
2. GitLab pipeline auto-deploys test from `main`.
3. Create and push release tag on GitHub, e.g. `v1.4.0`.
4. GitLab pipeline appears for that tag.
5. Approver triggers `deploy:prod` manually in GitLab.

## Security Notes

- Do not commit production secrets to GitHub.
- Keep production secrets in host `.env` and protected GitLab variables only.
- Use separate SSH keys for CI and limit key scope to deploy users.
- Keep production deploy job protected and approval-gated.
