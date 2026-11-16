from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.tenant import TenantMembership
from app.models.user import User
from app.services.events import manager

router = APIRouter(tags=["events"])


def _extract_token(websocket: WebSocket, query_token: str) -> tuple[str, str | None]:
    """Return `(jwt, subprotocol_to_echo)` for an incoming handshake.

    The subprotocol is preferred because uvicorn writes the full request line
    (including the query string) to its access log, so a token passed as a
    query parameter ends up in plain text in the logs.
    """
    offered = websocket.headers.get("sec-websocket-protocol", "")
    # Browsers send a comma-separated list when offering several subprotocols.
    if offered.strip():
        token = offered.split(",")[0].strip()
        return token, token
    # Nothing was offered: echoing a subprotocol anyway makes browsers abort
    # the handshake, so the legacy query-param path must echo none.
    return query_token, None


@router.websocket("/ws/events")
async def events_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
    session: Session = Depends(get_session),
):
    """Dashboard realtime feed.

    Authenticate with the JWT as the `Sec-WebSocket-Protocol` header (preferred)
    or, for older clients, as the `?token=` query parameter — the latter is
    deprecated because it is written to the server access log.

    Topics pushed: `stats` (one event per tenant after each health check
    cycle, carrying that tenant's counts) and `logs` (every gateway request).
    Both are filtered by the caller's tenant membership; a super admin sees
    every tenant.
    """
    subprotocol_token, echo = _extract_token(websocket, token)
    try:
        payload = decode_access_token(subprotocol_token)
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=4401)
        return

    user = session.get(User, user_id)
    if user is None:
        await websocket.close(code=4401)
        return

    # Resolve the tenant scope before the session is released. A non-admin sees
    # only the tenants they belong to; a super admin sees everything and needs
    # the unscoped feed (the tenant switcher would otherwise show one tenant's
    # logs for every other tenant). An admin with no membership still gets the
    # default tenant via `get_active_tenant_id`, but the feed must not depend on
    # a request header, so use the same membership set semantics.
    if user.is_admin:
        tenant_scope: set[int] | None = None
    else:
        tenant_scope = {
            m.tenant_id
            for m in session.exec(
                select(TenantMembership).where(TenantMembership.user_id == user.id)
            ).all()
        }

    # Release the pooled connection before the socket starts streaming. A
    # WebSocket lives for hours; holding the dependency's Session for that long
    # pins one connection per client until the pool is exhausted. The
    # dependency's `with` block tolerates this second close.
    session.close()

    await manager.connect(websocket, subprotocol=echo, tenant_scope=tenant_scope)
    try:
        while True:
            # Keep the connection alive; client messages are ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
