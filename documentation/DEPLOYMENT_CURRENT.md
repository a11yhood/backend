# Current Production Deployment Setup

## Overview

The a11yhood backend is deployed using GitHub Actions to build Docker images, which are then pulled and run on a production server. This approach solves the fuse-overlayfs Docker build issues on the server while maintaining security and automation.

## Critical Issue: Docker + fuse-overlayfs Incompatibility

**Status**: BLOCKING production deployment

### Problem
The production server (`slicomex.cs.washington.edu`) runs rootless Docker with the `fuse-overlayfs` storage driver. This configuration **cannot extract Python base images** due to permission errors:

```
failed to register layer: failed to Lchown '/etc/gshadow' for UID 0, GID 42: lchown /etc/gshadow: operation not permitted
```

### What We Know
- ✅ Docker is installed and partially functional
- ✅ Simple images work (`hello-world`, `busybox`)
- ❌ **ALL Python base images fail** (tried: python:3.9-3.14, slim/alpine/bullseye variants)
- ❌ Both `docker pull` and `docker load` fail with same error
- ❌ Building locally then loading via tar file also fails

### Root Cause
Fuse-overlayfs storage driver cannot handle `Lchown` operations on `/etc/gshadow` that occur in Python base image layers. This is a known limitation of fuse-overlayfs with certain image layer operations.

### Solutions (in priority order)

#### Option 1: Contact Server Admin (REQUIRED)
**Status**: Podman not available on server

Request admin assistance with one of the following:

**Recommended: Switch to overlay2 storage driver**
```bash
# Admin needs to stop Docker, change storage driver, and restart
sudo systemctl stop docker
sudo vi /etc/docker/daemon.json
# Add/modify: {"storage-driver": "overlay2"}
sudo rm -rf /var/lib/docker  # WARNING: Deletes all images/containers
sudo systemctl start docker
```

**Alternative: Enable rootful Docker**
```bash
# Give user access to rootful Docker group
sudo usermod -aG docker $USER
# Then restart Docker service
sudo systemctl restart docker
```

**Alternative: Install Podman**
```bash
sudo apt-get install -y podman
# or
sudo yum install -y podman
```

#### Admin Contact Email Template
```
Subject: Docker Storage Driver Issue on slicomex.cs.washington.edu

Hi,

I'm unable to deploy Python-based Docker containers on slicomex.cs.washington.edu 
due to a known issue with the fuse-overlayfs storage driver in rootless Docker.

Error: "failed to Lchown '/etc/gshadow' for UID 0, GID 42: operation not permitted"

Could you please help by implementing one of these solutions:

1. Switch Docker to overlay2 storage driver (preferred)
2. Enable rootful Docker access for my user
3. Install Podman as an alternative to Docker

Simple test case:
- Works: docker pull hello-world
- Fails: docker pull python:3.10-slim

Thank you!
```

#### Option 2: Build Custom Minimal Image (FALLBACK)
If admin support isn't available, we could build Python from source on busybox/alpine. This requires significant effort and may have compatibility issues. Not recommended unless absolutely necessary.

### Current Status
- GitHub Actions successfully builds images
- Images stored in ghcr.io/a11yhood/a11yhood-backend
- **Blocked**: Cannot deploy to production server until storage driver issue resolved

---

## Architecture

```
Developer → Git Push → GitHub Actions → GitHub Container Registry → Production Server
                         (Build)         (Store Image)            (Pull & Run)
```

## Components

### 1. GitHub Actions Workflow

**File**: `.github/workflows/docker-build.yml`

**Triggers on**:
- Pushes to `main` branch
- Manual workflow dispatch

**What it does**:
- Checks out code
- Builds Docker image using GitHub's infrastructure
- Pushes to GitHub Container Registry (ghcr.io)
- Tags with both `latest` and commit SHA

**Image location**: `ghcr.io/a11yhood/a11yhood-backend:latest`

### 2. Docker Image

**Base**: `python:3.9-slim-buster` (chosen for fuse-overlayfs compatibility)

**Security**:
- `.env` file excluded via `.dockerignore`
- Runs as non-root user (`appuser`)
- Environment variables passed at runtime, not baked into image
- Image visibility: **Private** (requires authentication to pull)

**Build process**: Handled entirely by GitHub Actions to avoid server-side build issues

### 3. Production Server

**Server**: slicomex
**User**: jmankoff
**Docker**: Rootless with fuse-overlayfs storage driver

**Authentication**:
```bash
# One-time setup: Login to GitHub Container Registry
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u YOUR_USERNAME --password-stdin
# PAT must have read:packages scope
```

**Deployment**:
```bash
# Pull latest image
docker pull ghcr.io/a11yhood/a11yhood-backend:latest

# Tag for local use
docker tag ghcr.io/a11yhood/a11yhood-backend:latest a11yhood-backend:latest

# Start production
./scripts/start-prod.sh
```

## Branch Strategy

### Main Branch

- **Protected**: Requires pull requests for all changes
- **No direct pushes**: Even for admins
- **Automatic builds**: Every merge triggers Docker image build

### Development Workflow

```bash
# 1. Create feature branch from main
git checkout main
git pull
git checkout -b feature/your-change

# 2. Make changes and commit
git add .
git commit -m "Your change"
git push -u origin feature/your-change

# 3. Create Pull Request on GitHub
# Base: main <- Compare: feature/your-change

# 4. Merge PR (triggers automatic build)

# 5. On server: Pull and deploy new image
docker pull ghcr.io/a11yhood/a11yhood-backend:latest
docker tag ghcr.io/a11yhood/a11yhood-backend:latest a11yhood-backend:latest
./scripts/start-prod.sh
```

## Environment Configuration

### Server `.env` File

Location: `/path/to/a11yhood-backend/.env`

**Critical**: This file is NOT in the Docker image and must exist on the server.

```bash
# Supabase Configuration
SUPABASE_URL=your-url
SUPABASE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key

# CORS - Frontend URLs
FRONTEND_URL=your-dev
PRODUCTION_URL=https://a11yhood.org
CORS_EXTRA_ORIGINS=https://a11yhood.github.io

# Production mode
TEST_MODE=false

# Secret key for JWT
SECRET_KEY=your-production-secret-key

# GitHub OAuth
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
```

### How Secrets Are Handled

1. **Build time**: No secrets in Dockerfile or image
2. **Runtime**: Secrets passed via:
   - `docker run --env-file .env` OR
   - Environment variables exported in start scripts (`./scripts/start-prod.sh`)

## Start Scripts

### `scripts/start-prod.sh`

Starts production container with:
- Port 8001 exposed
- Environment variables from `.env`
- Health checks
- Restart policy: unless-stopped

### `scripts/stop-prod.sh`

Stops and removes production container.

## Monitoring

**Health Check**:
```bash
curl [backend]/health
```

**Logs**:
```bash
docker logs a11yhood-backend-prod
docker logs -f a11yhood-backend-prod  # Follow mode
```

**Container Status**:
```bash
docker ps | grep a11yhood-backend-prod
```

## Security

### GitHub Security Settings

**Repository Settings** → **Actions** → **General**:
- ✅ Allow all actions and reusable workflows
- ✅ Require approval for first-time contributors

**Repository Settings** → **Branches**:
- ✅ Branch protection on `main`
- ✅ Require pull request before merging
- ✅ No bypassing for admins

**Repository Settings** → **Security**:
- ✅ Dependabot alerts enabled
- ✅ Dependabot security updates enabled
- ✅ Secret scanning enabled
- ✅ Push protection enabled

### Container Registry

**Package visibility**: Private
- Requires authentication to pull
- Code in public repo, but deployable image is private
- Prevents unauthorized deployments

**Authentication**: GitHub Personal Access Token with `read:packages` scope

### Server Security

- Rootless Docker (non-root user runs containers)
- Secrets in `.env` (not committed to git, not in image)
- File permissions: `.env` readable only by deployment user
- Container runs as non-root user `appuser` (UID 1000)

## Frontend Configuration

### GitHub Pages Setup

**Frontend URLs**:
- `https://a11yhood.org` (custom domain)
- `https://a11yhood.github.io/search/` (fallback)

**Backend CORS**: Both URLs allowed via `PRODUCTION_URL` and `CORS_EXTRA_ORIGINS`

**Supabase Configuration**:
1. Go to Supabase Dashboard → Authentication → URL Configuration
2. **Site URL**: `https://a11yhood.org`
3. **Redirect URLs**: Add both:
   - `https://a11yhood.org/*`
   - `https://a11yhood.github.io/*`

**GitHub OAuth**:
1. Go to GitHub Settings → Developer settings → OAuth Apps
2. **Homepage URL**: `https://a11yhood.org`
3. **Authorization callback URL**: `https://ztnxqktwvwlbepflxvzp.supabase.co/auth/v1/callback`

## Troubleshooting

### Build fails in GitHub Actions

**Check**: Repository Settings → Actions → Permissions
- Must allow third-party actions (checkout, login, build-push)

### Pull fails: "denied"

**Check**: GitHub PAT has `read:packages` scope
**Fix**: Create new token at https://github.com/settings/tokens

### Container won't start

**Check logs**:
```bash
docker logs a11yhood-backend-prod
```

**Common issues**:
- Missing `.env` file
- Invalid environment variables
- Port 8001 already in use

### CORS errors from frontend

**Check**: Frontend URL is in CORS allowlist
**Fix**: Add to `.env`:
```bash
CORS_EXTRA_ORIGINS=https://your-frontend-domain.com
```

Then restart:
```bash
./scripts/stop-prod.sh && ./scripts/start-prod.sh
```

## Updating Deployment

### Code Changes

```bash
# 1. Create PR to main branch
# 2. Merge PR (automatic build)
# 3. On server:
docker pull ghcr.io/a11yhood/a11yhood-backend:latest
docker tag ghcr.io/a11yhood/a11yhood-backend:latest a11yhood-backend:latest
./scripts/stop-prod.sh && ./scripts/start-prod.sh
```

### Configuration Changes

```bash
# On server: Edit .env
nano .env

# Restart to pick up changes
./scripts/stop-prod.sh && ./scripts/start-prod.sh
```

### Dependencies

Dependencies are in `requirements.txt`. Changes trigger automatic rebuild when merged to main.

## Future Improvements

### Potential Enhancements

1. **Automated deployment**: GitHub Actions could SSH to server and pull/restart automatically
2. **Multiple environments**: Staging environment with separate image tags
3. **Rollback capability**: Keep previous image tags for quick rollback
4. **Health check integration**: Auto-rollback if health checks fail after deployment
5. **Secrets management**: Use GitHub Actions secrets for sensitive build-time values

### Migration to Cloud

When ready to migrate from server to cloud hosting:
- Same Docker image works (no changes needed)
- Update `.env` with cloud provider endpoints
- Configure cloud provider to pull from ghcr.io
- Update DNS for a11yhood.org

The current setup is cloud-ready and portable.
