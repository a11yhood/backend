"""
Shared test data constants for backend and frontend tests.

This module defines all valid product types, sources, and categories
to ensure consistency across both backend and frontend test suites.

Frontend tests should import these constants when creating test products via API.
Backend tests use these for seeding the database.
"""

# Valid product sources (scrapers and user-submitted)
PRODUCT_SOURCES = {
    "github": "GitHub",
    "ravelry": "Ravelry",
    "thingiverse": "Thingiverse",
    "user-submitted": "User Submitted",
}

# Valid product types by source
PRODUCT_TYPES_BY_SOURCE = {
    "github": ["Software", "Tool", "Library"],
    "ravelry": ["Knitting", "Crochet", "Weaving"],
    "thingiverse": ["3D Print", "Fabrication", "Model"],
    "user-submitted": ["Software", "Pattern", "Tool", "3D Print", "Other"],
}

# Valid product types
PRODUCT_TYPES = [
    "Software",
    "Patterns",
    "3D Prints",
    "Tools",
    "Other",
    "Knitting",
    "Crochet",
    "Weaving",
    "3D Print",
    "Fabrication",
    "Model",
    "Tool",
    "Library",
]

# Default product types per source for seeding
DEFAULT_PRODUCT_TYPE_BY_SOURCE = {
    "github": "Software",
    "ravelry": "Knitting",
    "thingiverse": "3D Print",
    "user-submitted": "Other",
}

# Test product definitions for seeding
TEST_PRODUCTS = [
    {
        "name": "Test Product from GitHub",
        "description": "A test product from GitHub",
        "source": "github",
        "type": "Software",
        "source_url": "https://github.com/test/test-product",
    },
    {
        "name": "Test Product from Ravelry - Knitting",
        "description": "A test knitting pattern from Ravelry",
        "source": "ravelry",
        "type": "Knitting",
        "source_url": "https://www.ravelry.com/patterns/library/test-knit",
    },
    {
        "name": "Test Product from Ravelry - Crochet",
        "description": "A test crochet pattern from Ravelry",
        "source": "ravelry",
        "type": "Crochet",
        "source_url": "https://www.ravelry.com/patterns/library/test-crochet",
    },
    {
        "name": "Test Product from Thingiverse",
        "description": "A test 3D printable model from Thingiverse",
        "source": "thingiverse",
        "type": "3D Print",
        "source_url": "https://www.thingiverse.com/thing:test",
    },
]

# Test user definitions (matching seed_test_users.py)
TEST_USERS = [
    {
        "id": "49366adb-2d13-412f-9ae5-4c35dbffab10",
        "github_id": "admin-test-001",
        "username": "admin_user",
        "display_name": "Admin User",
        "email": "admin@example.com",
        "role": "admin",
    },
    {
        "id": "94e116f7-885d-4d32-87ae-697c5dc09b9e",
        "github_id": "mod-test-002",
        "username": "moderator_user",
        "display_name": "Moderator User",
        "email": "moderator@example.com",
        "role": "moderator",
    },
    {
        "id": "2a3b7c3e-971b-4b42-9c8c-0f1843486c50",
        "github_id": "user-test-003",
        "username": "regular_user",
        "display_name": "Regular User",
        "email": "user@example.com",
        "role": "user",
    },
]


def get_valid_product_type(source: str) -> str:
    """Get default/first valid product type for a source."""
    return DEFAULT_PRODUCT_TYPE_BY_SOURCE.get(source, "Other")


def get_valid_source() -> str:
    """Get first valid product source."""
    return list(PRODUCT_SOURCES.keys())[0]


def validate_product_type(source: str, product_type: str) -> bool:
    """Check if a product type is valid for a source."""
    valid_types = PRODUCT_TYPES_BY_SOURCE.get(source, [])
    return product_type in valid_types
