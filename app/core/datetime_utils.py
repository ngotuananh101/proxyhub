"""Datetime helpers shared by the API layer.

SQLite stores datetimes without their UTC offset and hands them back with
``tzinfo=None``. Calling ``.isoformat()`` on such a value emits an
offset-less string, which browsers parse as *local* time — shifting every
displayed timestamp by the viewer's UTC offset. Re-attaching UTC before
serializing keeps the instant correct.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_isoformat(value: datetime) -> str:
    """Serialize a datetime as an ISO string that always carries a UTC offset."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def is_valid_timezone(name: str) -> bool:
    """True if ``name`` resolves to an IANA timezone (e.g. ``Asia/Ho_Chi_Minh``)."""
    try:
        ZoneInfo(name)
    except Exception:
        return False
    return True
