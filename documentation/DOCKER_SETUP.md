# Simplified Docker Setup

This project uses a minimal Docker setup without Docker Compose for simplicity and ease of deployment.

## Architecture

- **Single Dockerfile**: Simplified, single-stage build for production
- **Plain Docker commands**: Uses `docker build` and `docker run` directly
- **No Docker Compose**: All configuration is in scripts and environment files

## Development Setup

Start the development server with hot-reload:

```bash
./scripts/start-dev.sh
```

The development server:
- Runs on `http://localhost:8000`
- Has hot-reload enabled (code changes auto-refresh)
- Uses `.env.test` for configuration
- Mounts the local source code for live editing

Stop the development server:

```bash
./scripts/stop-dev.sh
```

Reset the development database:

```bash
./scripts/start-dev.sh --reset-db
```

## Production Setup

Start the production server:

```bash
./scripts/start-prod.sh
```

The production server:
- Runs on `http://localhost:8000`
- Uses `.env` for configuration (production Supabase credentials)
- Runs with 4 workers for better performance
- Uses health checks for automatic restart

Stop the production server:

```bash
./scripts/stop-prod.sh
```

Skip the build if you already have the image:

```bash
./scripts/start-prod.sh --no-build
```

## Docker Image Details

### Development Image: `a11yhood-backend:dev`

- **Base**: Python 3.14-slim
- **Dependencies**: All development and testing packages
- **Port**: 8000
- **Reload**: Enabled with `--reload` flag
- **User**: Non-root `appuser` (UID 1000)

### Production Image: `a11yhood-backend:prod`

- **Base**: Python 3.14-slim
- **Dependencies**: Only production packages (no pytest, etc.)
- **Port**: 8000
- **Workers**: 4 worker processes
- **User**: Non-root `appuser` (UID 1000)

## Managing Containers

### View running containers

```bash
docker ps
```

### View logs

Development:
```bash
docker logs -f a11yhood-backend-dev
```

Production:
```bash
docker logs -f a11yhood-backend-prod
```

### Stop a specific container

```bash
docker stop a11yhood-backend-dev
docker rm a11yhood-backend-dev
```

### Remove all containers and images

```bash
docker stop a11yhood-backend-dev a11yhood-backend-prod 2>/dev/null
docker rm a11yhood-backend-dev a11yhood-backend-prod 2>/dev/null
docker rmi a11yhood-backend:dev a11yhood-backend:prod
```

## Building Images Manually

Build the development image:

```bash
docker build -t a11yhood-backend:dev --build-arg DOCKER_BUILDKIT=1 .
```

Build the production image:

```bash
docker build -t a11yhood-backend:prod .
```

## Dockerfile Structure

The simplified Dockerfile:

1. **Base stage**: Python 3.14-slim with system dependencies
2. **Install dependencies**: Uses `uv` for fast package installation
3. **Copy code**: Adds application source
4. **Security**: Runs as non-root user `appuser`
5. **Health checks**: Curl-based health endpoint monitoring
6. **Default command**: Runs `uvicorn` with 4 workers

## Environment Variables

Development (`.env.test`):
- `SUPABASE_URL`: Test database URL
- `SUPABASE_KEY`: Test database API key
- Other configuration as needed

Production (`.env`):
- `SUPABASE_URL`: Production database URL
- `SUPABASE_KEY`: Production database API key
- All other environment variables required for production

## Troubleshooting

### Port already in use

If port 8000 is already in use:

```bash
# Find what's using it
lsof -i :8000

# Or manually specify a different port in docker run
docker run -p 8080:8000 ...
```

### Build failures

If the Docker build fails:

1. Check Docker is running: `docker info`
2. Clear Docker cache: `docker system prune`
3. Try building manually: `docker build -t a11yhood-backend:prod .`
4. Check logs: See output from failed build

### Container won't start

Check the logs:
```bash
docker logs a11yhood-backend-dev  # or a11yhood-backend-prod
```

Common issues:
- Missing `.env` or `.env.test` file
- Wrong Supabase credentials
- Missing system dependencies

### Health check failures

The container has a health check endpoint at `/health`. If it's failing:

```bash
# Test manually
curl http://localhost:8000/health

# Check logs for errors
docker logs a11yhood-backend-dev
```

## Performance Considerations

- **uv for dependency management**: Much faster than pip
- **Slim base image**: Smaller Docker image size
- **Multi-worker production**: 4 workers for better throughput
- **Health checks**: Automatic restart on failure
- **Non-root user**: Better security, slightly less privileged

## Deployment

For cloud deployment (AWS, DigitalOcean, etc.):

1. Build the production image on your machine
2. Push to a container registry (Docker Hub, ECR, etc.)
3. Pull and run on the server:

```bash
docker pull your-registry/a11yhood-backend:prod
docker run \
  -d \
  --name a11yhood-backend \
  --env-file /path/to/.env \
  -p 8000:8000 \
  --restart always \
  your-registry/a11yhood-backend:prod
```

Or use the provided `start-prod.sh` script for consistency.
