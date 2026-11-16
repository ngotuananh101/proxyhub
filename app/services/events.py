import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from redis import Redis
from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "proxyhub:events"

# Topics whose payload belongs to one tenant. Anything else is broadcast to
# every socket; keep this closed rather than filtering on `tenant_id` alone so
# a future unscoped topic cannot be silently swallowed for members.
SCOPED_TOPICS = frozenset({"logs", "stats"})


class ConnectionManager:
    """Tracks connected dashboard WebSocket clients and broadcasts events."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        # Tenant ids each socket may see. `None` means every tenant (a super
        # admin), an empty set means none. Without this, every authenticated
        # socket received every tenant's request logs: host, path and client IP
        # of other tenants' traffic, which no UI filter can undo.
        self._tenant_scopes: dict[WebSocket, set[int] | None] = {}

    async def connect(
        self,
        websocket: WebSocket,
        subprotocol: str | None = None,
        tenant_scope: set[int] | None = None,
    ) -> None:
        """Accept a client, echoing `subprotocol` when one was offered.

        Echoing is required whenever the client proposed a subprotocol: browsers
        abort the handshake if the server accepts without one.
        """
        await websocket.accept(subprotocol=subprotocol)
        self.active.append(websocket)
        self._tenant_scopes[websocket] = tenant_scope

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)
        self._tenant_scopes.pop(websocket, None)

    def _may_see(self, websocket: WebSocket, payload: dict[str, Any]) -> bool:
        scope = self._tenant_scopes.get(websocket)
        if scope is None:
            return True
        tenant_id = payload.get("tenant_id")
        # An event with no tenant predates tenant tracking (legacy rows, or a
        # proxy whose tenant has not been adopted yet); only all-tenant clients
        # (scope is None) see it.
        return tenant_id is not None and tenant_id in scope

    async def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        message = {"topic": topic, "data": payload}
        dead: list[WebSocket] = []
        for ws in self.active:
            # Both topics carry tenant data: a log names the tenant that
            # proxied the request, a stats event counts one tenant's pool.
            if topic in SCOPED_TOPICS and not self._may_see(ws, payload):
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# Realtime events cross process boundaries: the Celery worker (stats) and the
# uvicorn threadpool (gateway log pushes) must reach WebSocket clients that
# live on the API process's main event loop. Redis pub/sub is the bridge:
# publishers PUBLISH from anywhere, and a relay task in the API process fans
# the messages out to its local clients.
_publish_client: Redis | None = None


def _get_publish_client() -> Redis:
    global _publish_client
    if _publish_client is None:
        _publish_client = Redis.from_url(settings.QUEUE_BROKER_URL)
    return _publish_client


def broadcast_sync(topic: str, payload: dict[str, Any]) -> None:
    """Publish an event from synchronous code (Celery tasks, sync endpoints)."""
    try:
        _get_publish_client().publish(
            CHANNEL, json.dumps({"topic": topic, "data": payload})
        )
    except Exception as e:
        logger.warning("Failed to publish realtime event: %s", e)


_relay_task: asyncio.Task | None = None


async def relay_events() -> None:
    """Subscribe to the event channel and fan messages out to local clients.

    Retries with backoff so a Redis hiccup does not kill the realtime feed.
    """
    backoff = 1.0
    while True:
        client = None
        try:
            client = aioredis.from_url(settings.QUEUE_BROKER_URL)
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            backoff = 1.0
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    await manager.broadcast(event["topic"], event["data"])
                except Exception:
                    logger.warning("Dropping malformed realtime event")
        except Exception as e:
            logger.warning("Realtime relay error (%s); retrying in %.0fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        finally:
            if client is not None:
                await client.aclose()


def start_relay() -> None:
    """Start the relay on the running event loop (called from the lifespan)."""
    global _relay_task
    _relay_task = asyncio.create_task(relay_events())


async def stop_relay() -> None:
    """Cancel the relay task (called from the lifespan shutdown)."""
    global _relay_task
    if _relay_task is None:
        return
    _relay_task.cancel()
    try:
        await _relay_task
    except (asyncio.CancelledError, Exception):
        pass
    _relay_task = None
