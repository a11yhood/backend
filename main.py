"""Main application entry point for a11yhood API.

Sets up FastAPI app with CORS middleware and routes for the accessible product community.
All endpoints are organized by domain in routers/ and use database_adapter for dual DB support.
"""
import uuid

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import load_settings_from_env, settings
from routers import (
    activities,
    blog_posts,
    collections,
    dev,
    discussions,
    images,
    product_urls,
    products,
    ratings,
    requests,
    scrapers,
    sources,
    users,
)
from services.auth import get_current_user
from services.database import get_db
from services.limiter import limiter
from services.scheduled_scrapers import get_scheduled_scraper_service

app = FastAPI(
    title="a11yhood API",
    version="1.0.0",
    description=(
        "API for a11yhood - Accessible Product Community\n\n"
        "Timestamp contract:\n"
        "- All API timestamps are UTC ISO 8601 strings with a time component.\n"
        "- Example: `2026-04-16T00:00:00+00:00`\n"
        "- Date-only strings such as `2026-04-16` are not part of the public API contract."
    )
)

import logging
import os

# Configure structured logging for the entire application
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Setup rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

logger = logging.getLogger(__name__)


def _should_run_scheduler() -> bool:
    """Return whether background scheduler should run in this process.

    Vercel serverless functions are ephemeral and not suitable for persistent
    background jobs. Allow explicit override via ENABLE_SCHEDULER=true.
    """
    if os.getenv("ENABLE_SCHEDULER", "").lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("VERCEL") != "1"


@app.on_event("startup")
async def validate_security_configuration():
    """Validate critical security settings on startup.

    Prevents common misconfigurations that could compromise security.
    Raises RuntimeError for critical issues that must be fixed before running.
    """
    # Reload settings within the function so tests that patch environment
    # (e.g., startup security tests) observe the updated values without
    # weakening production behavior.
    # Use a fresh settings instance so env patches in tests are respected.
    local_settings = load_settings_from_env()

    # Log CORS configuration status
    cors_origins = get_cors_origins()
    logger.info(f"CORS origins configured: {cors_origins}")

    # Detect production environment by checking for production indicators
    # We only consider it "production" if PRODUCTION_URL is configured.
    is_production = any([
        # Production domain in CORS
        local_settings.PRODUCTION_URL and
        "localhost" not in local_settings.PRODUCTION_URL and
        local_settings.PRODUCTION_URL.strip(),

        # Explicit production environment variable
        os.getenv("ENVIRONMENT") == "production",
        os.getenv("ENV") == "production",
    ])

    # CRITICAL: Prevent TEST_MODE in production
    if local_settings.TEST_MODE and is_production:
        raise RuntimeError(
            "🚨 CRITICAL SECURITY ERROR: TEST_MODE=true in production environment!\n"
            "\n"
            "This bypasses authentication and allows anyone to impersonate users.\n"
            "\n"
            "Action required:\n"
            "  1. Set TEST_MODE=false in your .env file\n"
            "  2. Restart the application\n"
            "\n"
            "Production detected due to:\n"
            f"  - SUPABASE_URL: {local_settings.SUPABASE_URL}\n"
            f"  - PRODUCTION_URL: {local_settings.PRODUCTION_URL}\n"
        )

    # CRITICAL: Validate SECRET_KEY in production
    if is_production:
        if local_settings.SECRET_KEY == "dev-secret-key-change-in-production":
            raise RuntimeError(
                "🚨 CRITICAL SECURITY ERROR: Default SECRET_KEY in production!\n"
                "\n"
                "Using the default key compromises JWT token security.\n"
                "\n"
                "Action required:\n"
                "  1. Generate a secure key:\n"
                "     python -c 'import secrets; print(secrets.token_hex(32))'\n"
                "  2. Set SECRET_KEY in your .env file\n"
                "  3. Restart the application\n"
            )

        if len(local_settings.SECRET_KEY) < 32:
            raise RuntimeError(
            f"🚨 CRITICAL SECURITY ERROR: SECRET_KEY too short ({len(local_settings.SECRET_KEY)} chars)!\n"
                "\n"
                "Production requires a SECRET_KEY of at least 32 characters.\n"
                "\n"
                "Action required:\n"
                "  1. Generate a secure key:\n"
                "     python -c 'import secrets; print(secrets.token_hex(32))'\n"
                "  2. Set SECRET_KEY in your .env file\n"
                "  3. Restart the application\n"
            )

    # Warnings for development mode
    if local_settings.TEST_MODE:
        logger.warning(
            "⚠️  TEST_MODE enabled - Development authentication active\n"
            "   - Dev tokens (dev-token-*) will be accepted\n"
            "   - Mock user accounts will be available\n"
            "   - NEVER enable TEST_MODE in production!\n"
        )

    if local_settings.SECRET_KEY == "dev-secret-key-change-in-production" and not is_production:
        logger.warning(
            "⚠️  Using default SECRET_KEY in development\n"
            "   This is OK for local testing but generate a unique key for staging/production.\n"
        )

    # Log security configuration status
    logger.info(
        f"Security configuration validated:\n"
        f"  - Production mode: {is_production}\n"
        f"  - TEST_MODE: {local_settings.TEST_MODE}\n"
        f"  - SECRET_KEY length: {len(local_settings.SECRET_KEY)} chars\n"
        f"  - CORS origins: {len(get_cors_origins())} configured\n"
    )

    # Initialize scheduled scrapers only in long-running process environments.
    if not local_settings.TEST_MODE and _should_run_scheduler():
        try:
            scheduler_service = get_scheduled_scraper_service()
            db = get_db()
            scheduler_service.initialize(db)
            scheduler_service.start()
            logger.info("Scheduled scraper service started")
        except Exception as e:
            logger.error(f"Failed to initialize scheduled scrapers: {e}")
            # Don't fail startup if scheduler fails, just log the error
    else:
        logger.info("Scheduled scrapers disabled for this environment")


@app.on_event("shutdown")
async def shutdown_scheduled_scrapers():
    """Stop scheduled scrapers on shutdown"""
    if not _should_run_scheduler():
        return

    try:
        scheduler_service = get_scheduled_scraper_service()
        scheduler_service.stop()
        logger.info("Scheduled scraper service stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduled scrapers: {e}")

def get_cors_origins():
    """Build strict CORS allowlist from environment.

    Security: Never use wildcard origins with credentials.
    Dev uses Vite proxy, so only HTTPS localhost needs direct CORS access.
    Production must explicitly set FRONTEND_URL and PRODUCTION_URL.
    """
    # Use only CORS_ORIGINS (comma-separated)
    origins = set()
    if settings.CORS_ORIGINS:
        origins.update(o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip())
    return list(origins)

# ============================================================================
# Security Middleware
# ============================================================================

# CORS middleware - must be added before app startup
# Guard against multiple additions (e.g., in tests that reload modules)
if not any(isinstance(m, type) and issubclass(m, type) and
           getattr(m, '__name__', None) == 'CORSMiddleware'
           for m in [type(middleware) for middleware in getattr(app, 'user_middleware', [])]):
    cors_origins = get_cors_origins()
    logger.info(f"CORS origins at startup: {cors_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy
    # In dev mode, relax CSP to allow Swagger/ReDoc UI and other dev tools
    if settings.TEST_MODE:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
    else:
        # Production: Allow CDN for Swagger/ReDoc UI documentation
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "frame-ancestors 'none'"
        )

    # HSTS (only in production with HTTPS)
    if not settings.TEST_MODE:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=()"
    )

    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    """Log and return structured request validation failures (HTTP 422)."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = exc.errors()

    first_error = errors[0] if errors else {}
    first_loc = ".".join(str(part) for part in first_error.get("loc", []))
    first_msg = first_error.get("msg", "Validation error")
    detail_message = (
        f"{first_loc}: {first_msg}" if first_loc else str(first_msg or "Validation error")
    )

    # For multipart uploads, capture actual form field names to diagnose field-name mismatches.
    form_field_names: list[str] | None = None
    content_type_header = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type_header or "application/x-www-form-urlencoded" in content_type_header:
        try:
            form = await request.form()
            form_field_names = list(form.keys())
        except Exception:
            form_field_names = ["<error reading form>"]

    logger.warning(
        "Request validation failed: %s %s request_id=%s content_type=%s content_length=%s"
        " form_fields=%s errors=%s",
        request.method,
        request.url.path,
        request_id,
        request.headers.get("content-type"),
        request.headers.get("content-length"),
        form_field_names,
        errors,
    )

    response = JSONResponse(
        status_code=422,
        content={
            "detail": detail_message,
            "message": detail_message,
            "errors": errors,
            "request_id": request_id,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response

# Trusted hosts (prevent host header injection)
allowed_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]
# Keep TestClient stable even when shell env vars temporarily override TEST_MODE.


def _extract_host(raw_value: str) -> str:
    """Normalize configured host values for TrustedHostMiddleware."""
    value = raw_value.strip()
    if not value:
        return ""
    return value.replace("https://", "").replace("http://", "").split("/")[0]

if settings.PRODUCTION_URL:
    host = _extract_host(settings.PRODUCTION_URL)
    if host:
        allowed_hosts.append(host)
if settings.FRONTEND_URL:
    host = _extract_host(settings.FRONTEND_URL)
    if host and host not in allowed_hosts:
        allowed_hosts.append(host)

# Optional explicit allowlist from environment/config.
# Example: ALLOWED_HOSTS=api.example.com,staging.example.com,*.vercel.app
if settings.ALLOWED_HOSTS:
    for raw_host in settings.ALLOWED_HOSTS.split(","):
        host = _extract_host(raw_host)
        if host and host not in allowed_hosts:
            allowed_hosts.append(host)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts
)

# Global exception handler
from services.error_handler import handle_exception

app.add_exception_handler(Exception, handle_exception)

# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
@limiter.limit("60/minute")  # Prevent abuse
async def root(request: Request):
    """API root endpoint."""
    return {
        "message": "a11yhood API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (no rate limit for monitoring)."""
    # Load fresh settings to report current mode
    current_settings = load_settings_from_env()

    # Detect production environment
    is_production = any([
        current_settings.SUPABASE_URL and
        "supabase.co" in current_settings.SUPABASE_URL and
        "dummy" not in current_settings.SUPABASE_URL,

        current_settings.PRODUCTION_URL and
        "localhost" not in current_settings.PRODUCTION_URL and
        current_settings.PRODUCTION_URL.strip(),

        os.getenv("ENVIRONMENT") == "production",
        os.getenv("ENV") == "production",
    ])

    return {
        "status": "healthy",
        "mode": "production" if is_production else "development",
        "test_mode": current_settings.TEST_MODE,
        "database": "supabase" if current_settings.SUPABASE_URL and "dummy" not in current_settings.SUPABASE_URL else "unconfigured"
    }


@app.get("/api/scraping-logs")
async def get_scraping_logs(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    source: str | None = None,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Backward-compatible scraping logs endpoint used by frontend.

    Mirrors /api/scrapers/logs semantics so older frontend paths still return real data.
    """
    query = db.table("scraping_logs").select("*")

    if source:
        query = query.eq("source", source)

    response = query.range(offset, offset + limit - 1).order("created_at", desc=True).execute()
    return response.data


@app.get("/api/scrapers/schedule")
async def get_scheduled_scrapers():
    """Get status of scheduled scrapers"""
    try:
        scheduler_service = get_scheduled_scraper_service()
        jobs = await scheduler_service.get_jobs()
        return {
            "status": "enabled" if scheduler_service.scheduler and scheduler_service.scheduler.running else "disabled",
            "jobs": jobs
        }
    except Exception as e:
        logger.error(f"Error getting scheduled scrapers status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "jobs": []
        }


# Include routers
app.include_router(products.router)
app.include_router(ratings.router)
app.include_router(discussions.router)
app.include_router(activities.router)
app.include_router(scrapers.router)
app.include_router(requests.router)
app.include_router(users.router)
app.include_router(product_urls.router)
app.include_router(collections.router)
app.include_router(blog_posts.router)
app.include_router(sources.router)
app.include_router(images.router)
if settings.TEST_MODE:
    app.include_router(dev.router)
    app.include_router(dev.test_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
