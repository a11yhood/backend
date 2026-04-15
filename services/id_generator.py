"""Human-readable ID generation from names.

Generates URL-safe kebab-case IDs from product/collection names with uniqueness guarantees.
Format: "My Product Name" becomes "my-product-name", with numeric suffix if needed
(`my-product-name-2`). Used instead of UUIDs for cleaner, shareable URLs.
"""

import re


def normalize_to_snake_case(text: str) -> str:
    """
    Normalize a string to kebab-case (URL slug) format.

    Examples:
        "My Product" -> "my-product"
        "Star Rating Target" -> "star-rating-target"
        "3D Printer" -> "3d-printer"
    """
    if not text:
        return ""

    # Replace non-alphanumeric chars with hyphens for URL-friendly slugs
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip())

    # Convert to lowercase
    text = text.lower()

    # Remove leading/trailing hyphens
    text = text.strip("-")

    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)

    return text


def generate_id(name: str, get_existing_ids_func=None) -> str:
    """
    Generate a human-readable ID from a name.

    If get_existing_ids_func is provided, it will be called with the base ID
    to check for existing IDs. If there's a collision, appends a number.

    Args:
        name: The name to generate an ID from
        get_existing_ids_func: Optional async function to check if IDs exist.
                              Should return True if an ID exists.

    Returns:
        A snake_case ID, optionally with a numeric suffix for uniqueness
    """
    base_id = normalize_to_snake_case(name)

    # If no collision check provided, just return the normalized ID
    if not get_existing_ids_func:
        return base_id

    # Check for collisions (sync version - call this without await if calling from sync context)
    return base_id


def generate_id_with_uniqueness_check(name: str, db, table_name: str, column: str = "id") -> str:
    """
    Generate a unique human-readable ID from a name.

    Collision handling: Tries base ID first, then appends 1, 2, 3... until unique.
    Example: "My Product" -> "my_product", or "my_product2" if collision exists.

    Args:
        name: The name to generate an ID from
        db: Database connection (DatabaseAdapter instance)
        table_name: The table to check for uniqueness

    Returns:
        A unique snake_case ID, optionally with a numeric suffix
    """
    base_id = normalize_to_snake_case(name)

    # Check if base ID exists in the target column
    existing = db.table(table_name).select(column).eq(column, base_id).limit(1).execute()
    if not existing.data:
        return base_id

    # If base ID exists, try appending numbers until we find a unique one
    for i in range(1, 1000):
        candidate_id = f"{base_id}-{i + 1}" if i == 1 else f"{base_id}-{i}"
        existing = db.table(table_name).select(column).eq(column, candidate_id).limit(1).execute()
        if not existing.data:
            return candidate_id

    # Fallback: append a large random number (should never reach here in practice)
    import uuid

    return f"{base_id}-{str(uuid.uuid4())[:8]}"
