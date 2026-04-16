from datetime import UTC, date, datetime, time
from typing import Annotated, Any

from pydantic import Field


TIMESTAMP_DESCRIPTION = (
    "UTC ISO 8601 timestamp with a time component. "
    "Example: 2026-04-16T00:00:00+00:00. "
    "Date-only strings such as 2026-04-16 are not part of the API contract."
)

ApiTimestamp = Annotated[
    datetime,
    Field(description=TIMESTAMP_DESCRIPTION, examples=["2026-04-16T00:00:00+00:00"]),
]

OptionalApiTimestamp = Annotated[
    datetime | None,
    Field(description=TIMESTAMP_DESCRIPTION, examples=["2026-04-16T00:00:00+00:00"]),
]


_TIMESTAMP_KEYS = frozenset(
    {
        "joined_at",
        "last_active",
        "publish_date",
        "source_last_updated",
        "timestamp",
        "token_expires_at",
    }
)


def is_timestamp_field(field_name: str) -> bool:
    return field_name.endswith("_at") or field_name in _TIMESTAMP_KEYS


def normalize_timestamp_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC).isoformat()

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return value

        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(candidate)
            except ValueError:
                return value
            return datetime.combine(parsed_date, time.min, tzinfo=UTC).isoformat()

        dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()

    return value


def normalize_timestamp_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_timestamp_fields(item) for item in value]

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and is_timestamp_field(key):
                normalized[key] = normalize_timestamp_value(item)
            else:
                normalized[key] = normalize_timestamp_fields(item)
        return normalized

    return value