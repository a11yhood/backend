# a11yhood Backend API

The a11yhood backend is designed to provide access to the a11yhood data and to support scraping of new data. See the a11yhood frontend (a11yhood/a11yhood.github.io) for the ux side of this project. 

Additional documentation files can be found in the documentation directory.

## Project Structure

```
a11yhood-backend/
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration and environment settings
├── database_adapter.py     # Supabase database adapter (prod + test)
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

- Docker (recommended) OR
- Python 3.14+ with pip/venv
- Supabase projects/credentials for production and test environments

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/a11yhood/a11yhood-backend.git
   cd a11yhood-backend
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings if needed
   ```

### Starting the Server

#### Option 1: Using Pixi Tasks (Recommended)

```bash
# Start development server against test Supabase (.env.test)
# The API will be available at http://localhost:8002/api

pixi run dev

# Start with database reset
pixi run dev-reset

# Start with seed data
pixi run dev-seed

# Start production server
# The API will be available at http://localhost:8001/api

pixi run prod

# Stop the server
pixi run dev-stop

# Stop production server
pixi run prod-stop
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
SUPABASE_DB_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require

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
- **[DEPLOYMENT_CURRENT.md](documentation/DEPLOYMENT_CURRENT.md)** - Production deployment guide
- **[CODE_STANDARDS.md](documentation/CODE_STANDARDS.md)** - Coding standards and conventions
- **[SECURITY_BEST_PRACTICES.md](documentation/SECURITY_BEST_PRACTICES.md)** - Security guidelines
- **[ARCHITECTURE.md](documentation/ARCHITECTURE.md)** - System architecture and design

For a complete index of all documentation, see [documentation/README.md](documentation/README.md).

## Testing

Run the test suite using pixi:

```bash
# Run all tests
pixi run test

# Run with additional pytest flags
pixi run test -- -v

# Run specific test
pixi run test -- -k test_name

# Run with coverage report
pixi run test -- --cov
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

a11yhood uses Supabase for both production and test environments.

1. **Production Supabase project** - `.env`
2. **Test Supabase project** - `.env.test`

`TEST_MODE` controls runtime behavior (dev tokens, scheduler behavior), not database engine.

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

For most development tasks, pixi handles setup automatically. If you need to install dependencies manually:

```bash
# Create virtual environment (if not using pixi)
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
pixi run dev
```

### Database Management

```bash
# Seed test data
python seed_scripts/seed_all.py

# Apply migrations
./scripts/apply-migrations.sh --env-file .env.test

# Optional: local Postgres for SQL migration validation 
./scripts/start-local-postgres.sh
SUPABASE_DB_URL=postgresql://postgres:postgres@localhost:5433/a11yhood ./scripts/apply-migrations.sh
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
2. Apply migration to both Supabase environments (test and production)
3. Update schema documentation
4. Update models if schema changes

## Troubleshooting

- **Port 8001 already in use**: Kill the process or use different port: `PORT=8002 python main.py`
- **Database connection error**: Check `SUPABASE_URL`/`SUPABASE_KEY` in `.env` (or `.env.test`) and verify project connectivity
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

1. Check existing [GitHub Issues](https://github.com/a11yhood/a11yhood-backend/issues)
2. Review [documentation/](documentation/) for existing guidance
3. Create a new issue with detailed information
4. For security issues, follow responsible disclosure

## Next Steps

- Check [documentation/LOCAL_TESTING.md](documentation/LOCAL_TESTING.md) for complete local setup
- Review [API_REFERENCE.md](documentation/API_REFERENCE.md) for endpoint details
- See [AGENT_GUIDE.md](documentation/AGENT_GUIDE.md) for development patterns
- Visit the [examples notebook](EXAMPLES.ipynb) for request/response examples

