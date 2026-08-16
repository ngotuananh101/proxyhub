from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.user import User
from app.services.events import manager

router = APIRouter(tags=["events"])


@router.websocket("/ws/events")
async def events_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
    session: Session = Depends(get_session),
):
    """Dashboard realtime feed. Authenticate with the JWT as ?token=...

    Topics pushed: `stats` (after each health check cycle) and `logs`
    (every gateway request).
    """
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))
    except Exception:
        await websocket.close(code=4401)
        return

    user = session.get(User, user_id)
    if user is None:
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; client messages are ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
