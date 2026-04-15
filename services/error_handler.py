"""Global error handler for sanitizing error messages.

Prevents information disclosure by hiding internal error details in production.
Logs full errors server-side for debugging while showing generic messages to clients.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings

logger = logging.getLogger(__name__)


async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler that sanitizes error messages.

    In production:
    - Returns generic error message to client
    - Logs full error details server-side

    In development (TEST_MODE):
    - Includes debug information in response
    - Helps developers troubleshoot issues
    """

    # Log full error server-side with request context
    logger.error(
        f"Request failed: {request.method} {request.url.path}",
        exc_info=exc,
        extra={
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
            "method": request.method,
            "path": request.url.path,
        },
    )

    # Return sanitized error to client
    if settings.TEST_MODE:
        # Development: include details for debugging
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "debug_info": str(exc),
                "type": type(exc).__name__,
            },
        )
    else:
        # Production: generic message only
        response = JSONResponse(
            status_code=500, content={"detail": "Internal server error occurred"}
        )

    # Add CORS headers to error responses so frontend can receive them
    origin = request.headers.get("origin")
    if origin:
        # Import here to avoid circular dependency
        from main import get_cors_origins

        allowed_origins = get_cors_origins()
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, PATCH, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = "*"

    return response
