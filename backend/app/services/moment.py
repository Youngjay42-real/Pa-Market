"""Datetime normalisation helpers.

SQLite (local tests, dev) returns naive datetimes while Postgres/Neon returns
timezone-aware ones. Every comparison against `datetime.now(timezone.utc)` has
to go through `as_utc` so behaviour is identical in both environments.
"""
from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to naive datetimes; pass aware values through."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
