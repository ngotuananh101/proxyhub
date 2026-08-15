from fastapi import APIRouter, Depends, Header, HTTPException, Query

from sqlmodel import Session

from app.core.database import get_session
from app.api.deps import verify_internal_key
from app.schemas.proxy import InternalProxyResponse
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
