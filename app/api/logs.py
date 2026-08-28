from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, func, or_, select

from app.api.deps import get_active_tenant_id, get_current_user
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.log import RequestLog
from app.models.user import User
from app.schemas.log import RequestLogListResponse, RequestLogResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _to_response(log: RequestLog) -> RequestLogResponse:
    return RequestLogResponse(
        id=log.id,
        tenant_id=log.tenant_id,
        client_ip=log.client_ip,
        method=log.method,
        host=log.host,
        path=log.path,
        proxy_host=log.proxy_host,
        proxy_port=log.proxy_port,
        response_bytes=log.response_bytes,
        created_at=utc_isoformat(log.created_at),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO datetime query param into naive UTC for comparison with the
    stored UTC timestamps. Returns None for empty/invalid values."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("", response_model=RequestLogListResponse)
def list_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    method: str | None = None,
    q: str | None = None,
    start: str | None = None,
    end: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    query = select(RequestLog).where(RequestLog.tenant_id == tenant_id)
    if method:
        query = query.where(RequestLog.method == method.upper())
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                col(RequestLog.host).ilike(pattern),
                col(RequestLog.path).ilike(pattern),
                col(RequestLog.proxy_host).ilike(pattern),
                col(RequestLog.client_ip).ilike(pattern),
            )
        )
    if start:
        start_dt = _parse_datetime(start)
        if start_dt is not None:
            query = query.where(col(RequestLog.created_at) >= start_dt)
    if end:
        end_dt = _parse_datetime(end)
        if end_dt is not None:
            query = query.where(col(RequestLog.created_at) < end_dt)

    query = query.order_by(RequestLog.id.desc())

    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    items = session.exec(query.offset((page - 1) * size).limit(size)).all()

    return RequestLogListResponse(
        items=[_to_response(log) for log in items],
        total=total,
        page=page,
        size=size,
    )
