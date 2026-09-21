from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_local(value: datetime, timezone_name: str) -> datetime:
    return ensure_utc(value).astimezone(ZoneInfo(timezone_name))


def format_local(value: datetime, timezone_name: str) -> str:
    return to_local(value, timezone_name).strftime("%Y-%m-%d %H:%M:%S")


def age_seconds(message_time: datetime, now: datetime | None = None) -> float:
    current = ensure_utc(now or utc_now())
    return (current - ensure_utc(message_time)).total_seconds()
