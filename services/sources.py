"""Utility functions for managing supported product sources."""

from urllib.parse import urlparse


def extract_domain(url: str) -> str | None:
    """Extract domain from URL (without www. prefix).

    Examples:
        https://www.ravelry.com/patterns/library/test -> ravelry.com
        https://github.com/user/repo -> github.com
        https://thingiverse.com/thing:123 -> thingiverse.com
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix if present
        if domain.startswith("www."):
            domain = domain[4:]

        return domain if domain else None
    except Exception:
        return None


def find_source_for_domain(domain: str, supported_sources: list[dict]) -> str | None:
    """Find source name for a given domain from supported sources list.

    Args:
        domain: Domain extracted from URL (e.g., 'github.com')
        supported_sources: List of dicts with 'domain' and 'name' keys

    Returns:
        Source name (e.g., 'Github') or None if not supported
    """
    domain_lower = domain.lower()
    for source in supported_sources:
        if source.get("domain", "").lower() == domain_lower:
            return source.get("name")
    return None
