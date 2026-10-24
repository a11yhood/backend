"""Short-lived in-process cache of the supported source names.

Every product list request needs the canonical source names, and that table almost never
changes. Handlers that change it call `invalidate_supported_sources_cache()`; the TTL covers
other workers/instances (each keeps its own copy) and edits made outside the API.
"""

import threading
import time

_TTL_SECONDS = 60

_lock = threading.Lock()
_cached: tuple[float, list[str]] | None = None


def get_supported_source_names(db) -> list[str]:
    """Return the supported source names, reading from the database at most once per TTL.

    Read errors propagate to the caller and are never cached, so one failed read cannot
    leave an empty list in place for a whole TTL.
    """
    global _cached
    with _lock:
        if _cached is not None and time.monotonic() - _cached[0] < _TTL_SECONDS:
            return list(_cached[1])

    rows = db.table("supported_sources").select("name").execute().data or []
    names = [str(row["name"]).strip() for row in rows if row.get("name") and str(row["name"]).strip()]

    with _lock:
        _cached = (time.monotonic(), names)
    return list(names)


def invalidate_supported_sources_cache() -> None:
    """Drop the cached names so the next read hits the database."""
    global _cached
    with _lock:
        _cached = None
