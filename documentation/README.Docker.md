# Docker Setup (No docker-compose)

This project uses plain Docker commands and repository scripts.
Do not use docker-compose for active development or deployment workflows.

## Prerequisites

- Docker Desktop (or compatible Docker engine)
- Access to Supabase test and production projects
- Configured environment files:
  - `.env.test` for dev/test (Supabase test project)
  - `.env` for production mode (Supabase production project)

## Development (Supabase Test Project)

Start development backend:

```bash
./scripts/start-dev.sh
```

Start with fresh test data:

```bash
./scripts/start-dev.sh --reset-db --seed
```

Stop development backend:

```bash
./scripts/stop-dev.sh
```

## Production Mode (Local Validation)

Start production backend using `.env`:

```bash
./scripts/start-prod.sh
```

Stop production backend:

```bash
./scripts/stop-prod.sh
```

## Build Images Manually (Optional)

Development image:

```bash
docker build -t a11yhood-backend:dev .
```

Production image:

```bash
docker build --target production -t a11yhood-backend:prod .
```

## Run Container Manually (Optional)

Run dev image directly:

```bash
docker run --rm -it \
  --name a11yhood-backend-dev \
  --env-file .env.test \
  -p 8000:8000 \
  a11yhood-backend:dev
```

Run prod image directly:

```bash
docker run --rm -d \
  --name a11yhood-backend-prod \
  --env-file .env \
  -p 8001:8000 \
  a11yhood-backend:prod
```

## Logs and Debugging

Follow logs:

```bash
docker logs -f a11yhood-backend-dev
docker logs -f a11yhood-backend-prod
```

Open shell in running container:

```bash
docker exec -it a11yhood-backend-dev bash
```

## Notes

- Runtime database path is Supabase-only (`SUPABASE_URL`/`SUPABASE_KEY`).
- Apply SQL migrations with:

```bash
./scripts/apply-migrations.sh --env-file .env.test
./scripts/apply-migrations.sh --env-file .env
```

- Prefer project scripts over manual Docker commands for consistent behavior.
