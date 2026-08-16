from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.database import get_session
from app.models.log import RequestLog
from app.models.user import User
from app.schemas.log import RequestLogResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _to_response(log: RequestLog) -> RequestLogResponse:
    return RequestLogResponse(
        id=log.id,
        client_ip=log.client_ip,
        method=log.method,
        host=log.host,
        path=log.path,
        proxy_host=log.proxy_host,
        proxy_port=log.proxy_port,
        response_bytes=log.response_bytes,
        created_at=log.created_at.isoformat(),
    )


@router.get("", response_model=list[RequestLogResponse])
def list_logs(
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    logs = session.exec(
        select(RequestLog).order_by(RequestLog.id.desc()).limit(limit)
    ).all()
    return [_to_response(log) for log in logs]
