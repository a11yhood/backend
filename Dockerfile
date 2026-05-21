# a11yhood backend Dockerfile
# Works in GitHub Actions CI/CD
# NOTE: Currently CANNOT be deployed to slicomex.cs.washington.edu due to
# fuse-overlayfs storage driver incompatibility. See documentation/DEPLOYMENT_CURRENT.md

# Use Python 3.13-slim (pyroaring has no Python 3.14 wheel and cannot compile from source on 3.14)
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install build dependencies needed for C extensions (e.g. pyroaring) and curl for uv installer
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Create non-root user early so COPY can set ownership directly
RUN groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock .

# Install Python dependencies from lockfile
RUN uv sync --frozen --no-dev

# Copy application code.
# In rootless Docker, avoid chown operations as they can fail on UID mapping.
# The app runs as appuser (UID 1000) which can read files copied here.
COPY . .

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

# Default command (overridden in development by start-dev.sh)
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
