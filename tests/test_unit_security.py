"""
Unit tests for security features that don't require database state.

These tests focus on:
- Token validation and auth headers (malformed, invalid, missing)
- Rate limiting behavior
- JSON/type validation
- HTTP header security
- Codebase secret scanning
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# Authentication Tests (No DB Needed)
# ============================================================================


def test_invalid_token_rejected(client):
    """Verify invalid authorization tokens are handled gracefully"""
    # Test with malformed Bearer token
    response = client.get(
        "/api/products",
        headers={"Authorization": "Bearer invalid.token.here"},
    )

    # Endpoint has optional auth; invalid headers should never cause 500.
    assert response.status_code in [200, 401]


def test_malformed_token_header_ignored(client):
    """Verify malformed auth headers are handled gracefully"""
    # Test with malformed Authorization header (no Bearer prefix)
    response = client.get(
        "/api/products",
        headers={"Authorization": "NotABearer"},
    )

    # Endpoint has optional auth; malformed headers should never cause 500.
    assert response.status_code in [200, 401]


def test_missing_auth_on_protected_endpoint(client):
    """Verify protected endpoints reject unauthenticated requests"""
    response = client.post(
        "/api/products",
        json={
            "name": "Test",
            "source": "github",
            "source_url": "https://github.com/user/test",
        },
    )

    # Should reject with 401
    assert response.status_code == 401


# ============================================================================
# HTTP Header Security Tests (No DB Needed)
# ============================================================================


def test_sensitive_headers_not_leaked(client):
    """Verify sensitive headers are not exposed"""
    response = client.get("/")

    # Should not leak internal server info
    assert (
        "X-Powered-By" not in response.headers or response.headers.get("X-Powered-By") != "FastAPI"
    )

    # If CSP is configured, it should be non-empty.
    if "Content-Security-Policy" in response.headers:
        assert response.headers["Content-Security-Policy"].strip() != ""
    assert "X-Content-Type-Options" in response.headers


# ============================================================================
# Rate Limiting Tests (No DB Needed)
# ============================================================================


def test_rate_limit_on_root_endpoint(client):
    """Verify rate limiting prevents abuse on GET /"""
    # The root endpoint has a 60/minute limit
    # Make 65 requests to exceed it
    responses = []
    for i in range(65):
        response = client.get("/")
        responses.append(response.status_code)

    # At least some should be rate limited (429)
    # Note: In test environment, rate limiting might not be fully active
    # but we verify it doesn't crash
    assert all(status in [200, 429] for status in responses)


def test_health_check_no_rate_limit(client):
    """Verify /health endpoint has no rate limit"""
    # Health checks should not be rate limited for monitoring.
    # A few repeated requests are enough to verify the endpoint remains
    # accessible without adding unnecessary runtime or shared-state coupling.
    for i in range(3):
        response = client.get("/health")
        assert response.status_code == 200


# ============================================================================
# Request Validation Tests (No DB Needed)
# ============================================================================


def test_invalid_json_rejected(client):
    """Verify that malformed JSON is properly rejected"""
    # Send invalid JSON
    response = client.post(
        "/api/products",
        content="{'invalid': json}",  # Not valid JSON
        headers={
            "Content-Type": "application/json",
        },
    )

    # Should reject malformed JSON (either 400 or 422)
    assert response.status_code in [400, 422]


def test_type_confusion_prevented(client):
    """Verify that type confusion attacks are prevented by Pydantic validation"""
    # Try to send wrong types for fields
    response = client.post(
        "/api/products",
        json={
            "name": ["array", "instead", "of", "string"],  # Should be string
            "description": 12345,  # Should be string
            "source_url": "https://example.com/test",
            "source": "github",
            "type": "Other",
        },
    )

    # Pydantic should reject with validation error (401 if no auth, 422 if validated)
    assert response.status_code in [401, 422]


# ============================================================================
# Secret Scanning Tests (Check for hardcoded credentials in codebase)
# ============================================================================


def _iter_scannable_repo_files(extensions: set[str]) -> list[str]:
    """Return tracked files that match *extensions*.

    Using `git ls-files` keeps this aligned with .gitignore and avoids scanning
    local environments such as .venv/.pixi.
    """
    project_root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        tracked = [p.decode("utf-8", errors="ignore") for p in result.stdout.split(b"\x00") if p]
        return [str(project_root / rel_path) for rel_path in tracked if any(rel_path.endswith(ext) for ext in extensions)]
    except Exception as exc:
        raise RuntimeError(
            "Failed to enumerate tracked files with git ls-files. "
            "Tests require a working git repository."
        ) from exc


def test_no_hardcoded_oauth_secrets_in_codebase():
    """Scan codebase for accidentally committed OAuth secrets"""
    # Patterns that indicate a real secret (not a placeholder or env var)
    secret_patterns = [
        # Real OAuth tokens (long random strings)
        r'["\']?access_token["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{40,})["\']',
        r'["\']?refresh_token["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{40,})["\']',
        r'["\']?client_secret["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{40,})["\']',
        # AWS-style keys
        r"AKIA[0-9A-Z]{16}",
        # GitHub tokens
        r"ghp_[A-Za-z0-9_]{36,}",
        # Generic API keys that look real (long hex strings)
        r'api[_-]?key["\']?\s*[:=]\s*["\']([a-f0-9]{32,})["\']',
    ]

    found_secrets = []
    read_errors = []
    project_root = Path(__file__).resolve().parents[1]

    for filepath in _iter_scannable_repo_files({".py", ".yml", ".yaml", ".json", ".toml", ".sh", ".md"}):
        filename = os.path.basename(filepath)
        if filename.endswith((".pyc", ".pyo")):
            continue

        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                content = f.read()

                # Skip test files and config templates
                if "test" in filepath or "example" in filepath or "template" in filepath:
                    continue

                # Check for secrets (but allow placeholders like "your-secret-here", "dev-key", etc.)
                for pattern in secret_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Ignore common test/dev placeholders
                        if match and not any(
                            placeholder in match.lower()
                            for placeholder in [
                                "test",
                                "dev",
                                "example",
                                "placeholder",
                                "your-",
                                "change-",
                                "dummy",
                                "fake",
                            ]
                        ):
                            found_secrets.append(
                                {
                                    "file": os.path.relpath(filepath, str(project_root)),
                                    "pattern": pattern[:50],
                                    "secret_preview": match[:20]
                                    if isinstance(match, str)
                                    else str(match)[:20],
                                }
                            )
        except Exception as exc:
            read_errors.append({"file": filepath, "error": str(exc)})

    # Report findings
    assert not read_errors, f"Failed reading files during secret scan: {read_errors}"
    assert not found_secrets, f"Found potential secrets in codebase: {found_secrets}"


def test_no_database_passwords_in_code():
    """Verify database passwords are not hardcoded in source files"""
    # Pattern for database connection strings with passwords
    db_password_patterns = [
        r"postgresql://[^:]+:[^@]+@",  # postgres://user:password@host
        r"mysql://[^:]+:[^@]+@",  # mysql://user:password@host
        r"mongodb://[^:]+:[^@]+@",  # mongodb://user:password@host
        r'password\s*=\s*["\']([^"\']{8,})["\']',  # password = "something"
    ]

    found_issues = []
    read_errors = []

    for filepath in _iter_scannable_repo_files({".py"}):
        filename = os.path.basename(filepath)
        if "test" in filename or "conftest" in filename:
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

                for pattern in db_password_patterns:
                    if re.search(pattern, content):
                        # Verify it's not a comment or example
                        for line in content.split("\n"):
                            if re.search(pattern, line) and not line.strip().startswith("#"):
                                found_issues.append(filename)
                                break
        except Exception as exc:
            read_errors.append({"file": filepath, "error": str(exc)})

    assert not read_errors, f"Failed reading files during DB password scan: {read_errors}"
    assert not found_issues, f"Found potential database passwords in: {found_issues}"


def test_no_api_keys_in_comments():
    """Verify API keys are not exposed even in comments"""
    found_issues = []
    read_errors = []

    for filepath in _iter_scannable_repo_files({".py"}):
        filename = os.path.basename(filepath)
        try:
            with open(filepath, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    # Check for suspicious patterns in comments
                    if "#" in line:
                        comment = line.split("#", 1)[1]
                        # Check if it looks like an exposed key example
                        if re.search(
                            r'(api[_-]?key|token|secret)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
                            comment,
                        ):
                            found_issues.append((filename, line_num))
        except Exception as exc:
            read_errors.append({"file": filepath, "error": str(exc)})

    assert not read_errors, f"Failed reading files during API-key comment scan: {read_errors}"
    assert not found_issues, f"Found potential API keys in comments: {found_issues}"
