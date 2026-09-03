from datetime import datetime, timezone
import logging
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
from app.services.gateway_auth_service import authenticate_gateway_request
from app.services.proxy_service import select_random_proxy
from app.services.settings_service import get_all as get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


# --- Legacy /internal/proxies (deprecated, kept for transition) ---

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

    settings_values = get_settings(session)
    default_target = str(settings_values.get("HEALTH_CHECK_URL", "https://api.ipify.org"))

    return InternalProxyResponse(
        id=proxy.id,
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
        default_target_url=default_target,
    )


# --- Combined Gateway Session Endpoint ---

class GatewaySessionRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    client_ip: str


class GatewaySessionProxy(BaseModel):
    id: int
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class GatewaySessionResponse(BaseModel):
    tenant_id: int
    credential_id: int
    auth_mode: str
    proxy: GatewaySessionProxy
    default_target_url: str


@router.post("/gateway/session", response_model=GatewaySessionResponse)
def create_gateway_session(
    body: GatewaySessionRequest,
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    """Authenticate client and select an alive proxy for the credential's tenant in 1 round trip."""
    verify_internal_key(x_internal_key)

    cred = authenticate_gateway_request(
        session=session,
        username=body.username,
        password=body.password,
        client_ip=body.client_ip,
    )
    if cred is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Select proxy scoped to credential's tenant
    proxy = select_random_proxy(session, tenant_id=cred.tenant_id)
    if proxy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No available proxy")

    # Update last_used_at on credential
    cred.last_used_at = datetime.now(timezone.utc)
    session.add(cred)
    session.commit()

    settings_values = get_settings(session)
    default_target = str(settings_values.get("HEALTH_CHECK_URL", "https://api.ipify.org"))

    return GatewaySessionResponse(
        tenant_id=cred.tenant_id,
        credential_id=cred.id,
        auth_mode=cred.auth_mode,
        proxy=GatewaySessionProxy(
            id=proxy.id,
            scheme=proxy.scheme,
            host=proxy.host,
            port=proxy.port,
            username=proxy.username,
            password=proxy.password,
        ),
        default_target_url=default_target,
    )


# --- Enriched Access Log Receiver ---

class GatewayLogEntry(BaseModel):
    tenant_id: int | None = None
    auth_credential_id: int | None = None
    auth_status: str | None = None
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
        tenant_id=log.tenant_id,
        auth_credential_id=log.auth_credential_id,
        auth_status=log.auth_status,
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
