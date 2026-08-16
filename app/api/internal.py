from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import verify_internal_key
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.log import RequestLog
from app.schemas.log import RequestLogResponse
from app.schemas.proxy import InternalProxyResponse
from app.services.events import broadcast_sync
from app.services.proxy_service import select_random_proxy

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/proxies", response_model=InternalProxyResponse)
def get_proxy_for_gateway(
    strategy: str = Query("random"),
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    verify_internal_key(x_internal_key)

    if strategy != "random":
        raise HTTPException(status_code=400, detail=f"Unsupported strategy: {strategy}")

    proxy = select_random_proxy(session)
    if proxy is None:
        raise HTTPException(status_code=404, detail="No available proxy")

    return InternalProxyResponse(
        id=proxy.id,
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
    )


class GatewayLogEntry(BaseModel):
    client_ip: str | None = None
    method: str | None = None
    host: str | None = None
    path: str | None = None
    proxy_host: str | None = None
    proxy_port: int | None = None
    response_bytes: int | None = None


@router.post("/logs", status_code=status.HTTP_201_CREATED)
def receive_gateway_log(
    body: GatewayLogEntry,
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    """Receive one access-log entry from the gateway plugin."""
    verify_internal_key(x_internal_key)

    log = RequestLog(**body.model_dump())
    session.add(log)
    session.commit()
    session.refresh(log)

    response = RequestLogResponse(
        id=log.id,
        client_ip=log.client_ip,
        method=log.method,
        host=log.host,
        path=log.path,
        proxy_host=log.proxy_host,
        proxy_port=log.proxy_port,
        response_bytes=log.response_bytes,
        created_at=utc_isoformat(log.created_at),
    )
    broadcast_sync("logs", response.model_dump())
    return response
