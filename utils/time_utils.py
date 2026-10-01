"""Timezone-safe date helpers."""
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


def iso_now() -> str:
    """Return current UTC time in ISO 8601 form."""
    return utc_now().isoformat()
