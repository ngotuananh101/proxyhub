from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, func, select

from app.api.deps import get_active_tenant_id, get_current_user
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.proxy import Proxy, ProxyStatus
from app.models.user import User
from app.schemas.proxy import (
    DeleteManyRequest,
    ImportRequest,
    ImportResult,
    ProxyCreate,
    ProxyListResponse,
    ProxyResponse,
    ProxyUpdate,
)
from app.services.proxy_service import import_proxies
from app.worker import check_all_proxies

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


def _proxy_to_response(p: Proxy) -> ProxyResponse:
    return ProxyResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        scheme=p.scheme,
        host=p.host,
        port=p.port,
        username=p.username,
        password=p.password,
        status=p.status.value,
        latency_ms=p.latency_ms,
        last_checked_at=utc_isoformat(p.last_checked_at) if p.last_checked_at else None,
        created_at=utc_isoformat(p.created_at),
        updated_at=utc_isoformat(p.updated_at),
    )


@router.post("", response_model=ProxyResponse, status_code=status.HTTP_201_CREATED)
def create_proxy(
    body: ProxyCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    existing = session.exec(
        select(Proxy).where(
            Proxy.tenant_id == tenant_id,
            Proxy.scheme == body.scheme,
            Proxy.host == body.host,
            Proxy.port == body.port,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proxy already exists")
    proxy = Proxy(**body.model_dump(), tenant_id=tenant_id)
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    return _proxy_to_response(proxy)


@router.get("", response_model=ProxyListResponse)
def list_proxies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: ProxyStatus | None = Query(None),
    scheme: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    query = select(Proxy).where(Proxy.tenant_id == tenant_id)
    if status:
        query = query.where(Proxy.status == status)
    if scheme:
        query = query.where(Proxy.scheme == scheme)
    if q:
        query = query.where(col(Proxy.host).contains(q))

    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    items = session.exec(query.offset((page - 1) * size).limit(size)).all()

    return ProxyListResponse(
        items=[_proxy_to_response(p) for p in items],
        total=total,
        page=page,
        size=size,
    )


@router.post("/import", response_model=ImportResult)
def import_proxies_endpoint(
    body: ImportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    return import_proxies(session, body.text, tenant_id=tenant_id)


@router.post("/check-all", status_code=status.HTTP_202_ACCEPTED)
def trigger_check_all(_: User = Depends(get_current_user)):
    result = check_all_proxies.delay()
    return {"detail": "Health check started", "task_id": result.id}


@router.post("/clear-dead")
def clear_dead_proxies(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    """Delete every proxy currently marked dead."""
    dead = session.exec(
        select(Proxy).where(Proxy.status == ProxyStatus.DEAD, Proxy.tenant_id == tenant_id)
    ).all()
    for proxy in dead:
        session.delete(proxy)
    session.commit()
    return {"deleted": len(dead)}


@router.get("/{proxy_id}", response_model=ProxyResponse)
def get_proxy(
    proxy_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy or proxy.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return _proxy_to_response(proxy)


@router.put("/{proxy_id}", response_model=ProxyResponse)
def update_proxy(
    proxy_id: int,
    body: ProxyUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy or proxy.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proxy not found")

    update_data = body.model_dump(exclude_unset=True)

    # Validate scheme
    if "scheme" in update_data and update_data["scheme"] not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Scheme must be http or https")

    # Validate status → convert to enum
    if "status" in update_data:
        try:
            update_data["status"] = ProxyStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Status must be alive, dead, or unknown",
            )

    # Check unique constraint when scheme/host/port changes
    new_scheme = update_data.get("scheme", proxy.scheme)
    new_host = update_data.get("host", proxy.host)
    new_port = update_data.get("port", proxy.port)
    if (new_scheme, new_host, new_port) != (proxy.scheme, proxy.host, proxy.port):
        conflict = session.exec(
            select(Proxy).where(
                Proxy.tenant_id == tenant_id,
                Proxy.scheme == new_scheme,
                Proxy.host == new_host,
                Proxy.port == new_port,
                Proxy.id != proxy_id,
            )
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="Proxy already exists")

    for key, value in update_data.items():
        setattr(proxy, key, value)
    proxy.updated_at = datetime.now(timezone.utc)
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    return _proxy_to_response(proxy)


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proxy(
    proxy_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy or proxy.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proxy not found")
    session.delete(proxy)
    session.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_many_proxies(
    body: DeleteManyRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
):
    for proxy_id in body.ids:
        proxy = session.get(Proxy, proxy_id)
        if proxy and proxy.tenant_id == tenant_id:
            session.delete(proxy)
    session.commit()
