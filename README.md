# a11yhood Backend API

The a11yhood backend is designed to provide access to the a11yhood data and to support scraping of new data. See the a11yhood frontend (a11yhood/a11yhood.github.io) for the ux side of this project. 

Additional documentation files can be found in the documentation directory.

## Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration and environment settings
├── database_adapter.py     # Database access wrapper used by the API and scripts
├── requirements.txt       # Python dependencies
├── pyproject.toml        # Project metadata and dependencies
│
├── models/                # Data models
│   ├── activities.py
│   ├── blog_posts.py
│   ├── collections.py
│   ├── discussions.py
│   ├── product_urls.py
│   ├── products.py
│   ├── ratings.py
│   ├── reviews.py
│   ├── scrapers.py
│   ├── sources.py
│   └── users.py
│
├── routers/               # API route handlers
│   ├── activities.py
│   ├── blog_posts.py
│   ├── collections.py
│   ├── discussions.py
│   ├── product_urls.py
│   ├── products.py
│   ├── ratings.py
│   ├── requests.py
│   ├── scrapers.py
│   ├── sources.py
│   └── users.py
│
├── services/              # Business logic and utilities
│   ├── auth.py           # Authentication handling
│   ├── database.py       # Database connections
│   ├── scrapers.py       # Scraping logic
│   ├── sources.py        # Source management
│   ├── scheduled_scrapers.py  # Scheduled scraping jobs
│   ├── security_logger.py     # Security event logging
│   ├── error_handler.py
│   ├── id_generator.py
│   └── sanitizer.py      # HTML/text sanitization
│
├── scrapers/              # Platform-specific scrapers
│   ├── base_scraper.py
│   ├── github.py
│   ├── goat.py
│   ├── ravelry.py
│   ├── thingiverse.py
│   └── scraper.py
│
├── migrations/            # Database migration scripts
├── scripts/              # Utility scripts
├── seed_scripts/         # Database seeding scripts
├── tests/                # Test suite
├── documentation/        # Detailed documentation
└── certs/               # SSL certificates for development
```

## Quick Start

### Prerequisites

- Docker & Docker Compose (recommended) OR
- Python 3.14+ with pip/venv
- Supabase/PostgreSQL access for development and production workflows

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/a11yhood/backend.git
   cd backend
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings if needed
   ```

### Starting the Server

#### Option 1: Using Scripts (Recommended)

```bash
# Start development server
# The API will be available at `https://localhost:8000/api`

./scripts/start-dev.sh

# Start with database reset
./scripts/start-dev.sh --reset-db

# Start production server
# The API will be available at `https://localhost:8001/api`

./scripts/start-prod.sh

# Start production server using the compiled docker image on github
# The API will be available for external use

./scripts/start-prod.sh --no-build

# Stop the server
./scripts/stop-dev.sh
```

#### Option 2: Manual Python Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run directly
python main.py
# Or with uvicorn:
uvicorn main:app --reload --ssl-keyfile=localhost+2-key.pem --ssl-certfile=localhost+2.pem
```

## API Documentation

The API is organized into the following resource groups:

### Core Resources

| Resource | Endpoint | Purpose |
|----------|----------|---------|
| **Users** | `/api/users` | User profiles and authentication |
| **Products** | `/api/products` | Product listings, search, filtering |
| **Sources** | `/api/sources` | Product source platforms (GitHub, Ravelry, etc.) |
| **Ratings** | `/api/ratings` | Product ratings and credibility |
| **Reviews** | `/api/reviews` | Detailed product reviews |
| **Collections** | `/api/collections` | User-created product collections |
| **Discussions** | `/api/discussions` | Threaded discussions about products |
| **Scrapers** | `/api/scrapers` | Web scraper management |
| **Blog Posts** | `/api/blog_posts` | Community blog content |
| **Activities** | `/api/activities` | User activity feed |

### Authentication

Most endpoints require authentication via OAuth (GitHub) or JWT tokens. Include the authorization header:

```
Authorization: Bearer <token>
```

## 🔧 Configuration

Configuration is managed via environment variables in `.env`:

```env
# Server
ENVIRONMENT=development
HOST=localhost
PORT=8001

# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key

# OAuth
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...

# API Keys
SUPABASE_URL=...
SUPABASE_KEY=...

# CORS
ALLOWED_ORIGINS=http://localhost:4173,https://localhost:4173
```

See `.env.example` for a complete list of configuration options.

## 📖 Documentation

## Starter Guides
- [QUICK_START.md](documentation/QUICK_START.md) — One-command startup, URLs, seeded users, quick troubleshooting
- [LOCAL_TESTING.md](documentation/LOCAL_TESTING.md) — Full local setup, env vars, test data seeding, common tasks
- [DEVELOPER_GUIDE.md](documentation/DEVELOPER_GUIDE.md) — End-to-end development workflow
- [PRD.md](documentation/PRD.md) — Product requirements
- [AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) — What an agent should read and the helper conventions to follow

Additional documentation in the `documentation/` folder:

- **[LOCAL_TESTING.md](documentation/LOCAL_TESTING.md)** - Local development and testing guide
- **[API_REFERENCE.md](documentation/API_REFERENCE.md)** - Detailed API endpoint reference
- **[CODE_STANDARDS.md](documentation/CODE_STANDARDS.md)** - Coding standards and conventions
- **[SECURITY_BEST_PRACTICES.md](documentation/SECURITY_BEST_PRACTICES.md)** - Security guidelines
- **[ARCHITECTURE.md](documentation/ARCHITECTURE.md)** - System architecture and design

For additional documentation, use the guides listed above and browse the `documentation/` folder directly.

## Developer Release Workflow (Tag-Based)

This repository publishes release artifacts from tags, not from every merge to `main`.

### What runs automatically

- Pull request to `main`: validation/build checks run.
- Push tag `v*`: Docker image publish workflow runs.
- There is currently no repository workflow triggered by `db-v*` tags.

### Day-to-day developer steps

1. Open a PR to `main` and wait for checks to pass.
2. Merge the PR.
3. If you want to publish an app image, create and push an app tag:

```bash
git checkout main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

4. If you want to publish DB exports, create and push a DB tag:

```bash
git checkout main
git pull
git tag db-vX.Y.Z
git push origin db-vX.Y.Z
```

### Notes

- Use semantic versioning for both app and DB tags.
- Cut tags from up-to-date `main` only.
- Do not push release tags from feature branches.

## Testing

Run the test suite using the provided script:

```bash
# Run all tests
./scripts/run-tests.sh

# Run with verbose output
./scripts/run-tests.sh -v

# Run specific test
./scripts/run-tests.sh -k test_name

# Run with coverage report
./scripts/run-tests.sh --cov

# Show help
./scripts/run-tests.sh --help
```

Key test commands are documented in [documentation/QUICK_TEST_GUIDE.md](documentation/QUICK_TEST_GUIDE.md).

## Security

This project prioritizes security and accessibility:

- **CORS** - Restricted to trusted origins
- **Rate Limiting** - API rate limiting via slowapi
- **SQL Injection Prevention** - SQLAlchemy parameterized queries
- **XSS Protection** - HTML sanitization via bleach
- **Authentication** - OAuth 2.0 and JWT tokens
- **HTTPS** - SSL/TLS for all communications

See [documentation/SECURITY_BEST_PRACTICES.md](documentation/SECURITY_BEST_PRACTICES.md) for detailed security information.

## Database

a11yhood uses Supabase/PostgreSQL for both production and the shared test environment.

Database schema and migrations:
- Schema: [supabase-schema.sql](supabase-schema.sql)
- Migrations: [migrations/](migrations/) directory

## Scrapers

The platform includes scrapers for multiple sources:

- **GitHub** - Open-source accessible projects
- **Ravelry** - Accessible crafting patterns
- **Thingiverse** - Accessible 3D printable designs

Scrapers run on a schedule and can be manually triggered. See [documentation/AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) for scraper management.

## For Developers

### Setting Up Development Environment

For most development tasks, the provided scripts handle setup automatically. If you need to install dependencies manually:

```bash
# Create virtual environment (if not using scripts)
python3 -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install -e .  # Install in editable mode

# Set up pre-commit hooks (recommended)
git config core.hooksPath .git/hooks
```

### Running with Hot Reload

The development server automatically reloads on code changes:

```bash
./scripts/start-dev.sh
```

### Database Management

```bash
# Seed test data
python seed_scripts/seed_all.py

# Reset the test database from the checked-in snapshot
pixi run reset
```

### Making Changes

1. Follow [documentation/CODE_STANDARDS.md](documentation/CODE_STANDARDS.md)
2. Create tests in `tests/`
3. Run tests locally before pushing
4. Update documentation for API changes

## Common Tasks

### Add a New API Endpoint

1. Create a route handler in `routers/`
2. Define models in `models/`
3. Add business logic in `services/`
4. Write tests in `tests/`
5. Document in [documentation/API_REFERENCE.md](documentation/API_REFERENCE.md)

### Add a New Scraper

1. Create scraper class in `scrapers/` extending `BaseScraper`
2. Add source configuration
3. Register in scraper registry
4. Add tests for scraper functionality

### Database Changes

1. Create migration file in `migrations/` with timestamp prefix
2. Apply migration to the production and test Supabase projects
3. Update schema documentation
4. Update models if schema changes

## Troubleshooting

- **Port 8001 already in use**: Kill the process or use different port: `PORT=8002 python main.py`
- **Database connection error**: Check your Supabase credentials in `.env` or `.env.test`, and set `SUPABASE_DB_URL` when a direct Postgres connection is required
- **CORS errors**: Verify `ALLOWED_ORIGINS` in `.env` includes your frontend URL
- **Scraper failures**: Check scraper logs and network connectivity

See [documentation/LOCAL_TESTING.md](documentation/LOCAL_TESTING.md) for more troubleshooting help.

## Performance & Monitoring

- Rate limiting is configured via `slowapi`
- Database queries are optimized with indexes
- Scheduled scrapers run asynchronously
- Activities and events are logged for debugging

## Contributing

Please follow the [CODE_STANDARDS.md](documentation/CODE_STANDARDS.md) and ensure:

1. All tests pass locally
2. Code follows the project standards
3. Documentation is updated
4. Commit messages are clear and descriptive

## License

This project is licensed under the [LICENSE](LICENSE) file in this repository.

##Support & Issues

For issues, questions, or feature requests:

1. Check existing [GitHub Issues](https://github.com/a11yhood/backend/issues)
2. Review [documentation/](documentation/) for existing guidance
3. Create a new issue with detailed information
4. For security issues, follow responsible disclosure

## Next Steps

- Check [documentation/LOCAL_TESTING.md](documentation/LOCAL_TESTING.md) for complete local setup
- Review [API_REFERENCE.md](documentation/API_REFERENCE.md) for endpoint details
- See [AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) for development patterns
- Visit the [examples notebook](EXAMPLES.ipynb) for request/response examples

