from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlmodel import Session, col

from app.models.log import RequestLog


def purge_old_request_logs(session: Session, retention_days: int) -> int:
    """Delete request logs older than the retention period. 0 disables removal.

    Deletes in one bulk statement: the table can hold one row per proxied
    request, and loading them all into memory just to delete them would not
    scale.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = session.exec(
        delete(RequestLog).where(col(RequestLog.created_at) < cutoff)
    )
    session.commit()
    return result.rowcount or 0
