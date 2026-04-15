"""Content sanitization to prevent XSS attacks.

Uses bleach library to sanitize HTML content while preserving safe formatting.
All user-generated content should be sanitized before storage.
"""

import bleach

# Allowed HTML tags for markdown rendering
# These are safe tags that won't execute scripts
ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "img",
]

# Allowed attributes for each tag
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],  # For syntax highlighting
}

# Allowed URL protocols
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(content: str | None) -> str | None:
    """Sanitize HTML content to prevent XSS attacks.

    Removes dangerous tags and attributes while preserving safe formatting.
    Use for content that should allow some HTML (discussions, blog posts).

    Args:
        content: HTML content to sanitize

    Returns:
        Sanitized HTML content safe for rendering
    """
    if not content:
        return content

    return bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,  # Remove disallowed tags entirely
    )


def sanitize_text(content: str | None) -> str | None:
    """Sanitize plain text content (strip all HTML).

    Removes all HTML tags and returns plain text only.
    Use for fields that should never contain HTML (names, titles).

    Args:
        content: Text content that may contain HTML

    Returns:
        Plain text with all HTML removed
    """
    if not content:
        return content

    return bleach.clean(content, tags=[], strip=True)


def sanitize_url(url: str | None) -> str | None:
    """Sanitize URL to prevent javascript: and data: URIs.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL or None if invalid
    """
    if not url:
        return url

    url = url.strip()

    # Reject javascript: and data: URIs
    if url.lower().startswith(("javascript:", "data:", "vbscript:")):
        return None

    return url
