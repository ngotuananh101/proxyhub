import asyncio
import json
import secrets
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.testclient import WebSocketDisconnect

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.services.events import CHANNEL, manager


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch):
    """Keep broadcast_sync and the relay off a real Redis in tests."""
    import app.services.events as events

    fake = MagicMock()
    fake.publish.return_value = 1
    monkeypatch.setattr(events, "_get_publish_client", lambda: fake)

    class _FakeAsyncRedis:
        @staticmethod
        def from_url(url):
            raise ConnectionError("redis disabled in tests")

    monkeypatch.setattr(events.aioredis, "from_url", _FakeAsyncRedis.from_url)
    return fake


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(name="token")
def token_fixture(engine, client):
    with Session(engine) as session:
        session.add(User(username="wsuser", hashed_password=hash_password("wspass123")))
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "wsuser", "password": "wspass123"})
    return resp.json()["access_token"]


def _make_token(engine) -> str:
    """Create a user and mint a token directly, bypassing the login endpoint."""
    with Session(engine) as session:
        user = User(
            username=f"user-{secrets.token_hex(4)}",
            hashed_password=hash_password("pw"),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return create_access_token({"sub": str(user.id)})


class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.accepted = False
        self.accepted_subprotocol: str | None = None
        self.sent: list[dict] = []
        self.fail = fail

    async def accept(self, subprotocol=None):
        self.accepted = True
        self.accepted_subprotocol = subprotocol

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("connection gone")
        self.sent.append(message)


class TestConnectionManager:
    async def test_connect_accepts_and_tracks(self):
        m = type(manager)()
        ws = FakeWebSocket()
        await m.connect(ws)
        assert ws.accepted
        assert m.active == [ws]

    async def test_connect_echoes_requested_subprotocol(self):
        # Browsers abort the handshake if the server picks a subprotocol the
        # client did not offer, so accept() must echo exactly what was sent.
        m = type(manager)()
        ws = FakeWebSocket()
        await m.connect(ws, subprotocol="jwt-token")
        assert ws.accepted_subprotocol == "jwt-token"

    async def test_disconnect_removes_and_tolerates_unknown(self):
        m = type(manager)()
        ws = FakeWebSocket()
        await m.connect(ws)
        m.disconnect(ws)
        assert m.active == []
        m.disconnect(ws)  # already gone: no error

    async def test_broadcast_sends_topic_envelope(self):
        m = type(manager)()
        a, b = FakeWebSocket(), FakeWebSocket()
        await m.connect(a)
        await m.connect(b)
        await m.broadcast("stats", {"total": 3})
        assert a.sent == [{"topic": "stats", "data": {"total": 3}}]
        assert b.sent == [{"topic": "stats", "data": {"total": 3}}]

    async def test_broadcast_drops_dead_clients(self):
        m = type(manager)()
        good, dead = FakeWebSocket(), FakeWebSocket(fail=True)
        await m.connect(good)
        await m.connect(dead)
        await m.broadcast("logs", {"id": 1})
        assert good.sent == [{"topic": "logs", "data": {"id": 1}}]
        assert m.active == [good]  # dead client removed


class TestBroadcastSync:
    def test_publishes_json_envelope(self, _no_real_redis):
        from app.services.events import broadcast_sync

        broadcast_sync("stats", {"total": 1})

        fake = _no_real_redis
        assert fake.publish.call_count == 1
        channel, raw = fake.publish.call_args.args
        assert channel == CHANNEL
        assert json.loads(raw) == {"topic": "stats", "data": {"total": 1}}

    def test_swallows_publish_errors(self, monkeypatch):
        import app.services.events as events

        failing = MagicMock()
        failing.publish.side_effect = ConnectionError("redis down")
        monkeypatch.setattr(events, "_get_publish_client", lambda: failing)

        events.broadcast_sync("stats", {"total": 1})  # must not raise


class _FakePubsub:
    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed: list[str] = []

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def listen(self):
        for m in self._messages:
            yield m
        raise ConnectionError("stream ended")


class _FakeAsyncClient:
    def __init__(self, messages):
        self._pubsub = _FakePubsub(messages)
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


class TestRelay:
    @staticmethod
    def _abort_after_first_retry(monkeypatch):
        """Break the relay's infinite retry loop once the fake stream ends."""
        import app.services.events as events

        async def _abort(delay):
            raise asyncio.CancelledError()

        monkeypatch.setattr(events.asyncio, "sleep", _abort)

    async def test_relay_fans_messages_to_local_clients(self, monkeypatch):
        import app.services.events as events

        message = {
            "type": "message",
            "data": json.dumps({"topic": "stats", "data": {"alive": 2}}),
        }
        fake_client = _FakeAsyncClient([{"type": "subscribe", "data": 1}, message])
        monkeypatch.setattr(events.aioredis, "from_url", lambda url: fake_client)
        broadcast = AsyncMock()
        monkeypatch.setattr(events.manager, "broadcast", broadcast)
        self._abort_after_first_retry(monkeypatch)

        with pytest.raises(asyncio.CancelledError):
            await events.relay_events()

        assert fake_client._pubsub.subscribed == [CHANNEL]
        broadcast.assert_awaited_once_with("stats", {"alive": 2})
        assert fake_client.closed

    async def test_relay_drops_malformed_messages(self, monkeypatch):
        import app.services.events as events

        fake_client = _FakeAsyncClient([{"type": "message", "data": b"not-json"}])
        monkeypatch.setattr(events.aioredis, "from_url", lambda url: fake_client)
        broadcast = AsyncMock()
        monkeypatch.setattr(events.manager, "broadcast", broadcast)
        self._abort_after_first_retry(monkeypatch)

        with pytest.raises(asyncio.CancelledError):
            await events.relay_events()

        broadcast.assert_not_awaited()

    async def test_start_and_stop_relay(self):
        import app.services.events as events

        events.start_relay()
        task = events._relay_task
        assert task is not None and not task.done()
        await events.stop_relay()
        assert task.cancelled()
        assert events._relay_task is None


class TestWebSocketEndpoint:
    def test_valid_token_connects_and_registers(self, client, token):
        with client.websocket_connect(f"/ws/events?token={token}"):
            assert len(manager.active) == 1
        assert manager.active == []  # removed on disconnect

    def test_missing_token_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/events"):
                pass
        assert excinfo.value.code == 4401

    def test_invalid_token_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/events?token=garbage"):
                pass
        assert excinfo.value.code == 4401

    def test_token_for_deleted_user_rejected(self, client, engine, token):
        with Session(engine) as session:
            for user in session.exec(select(User)).all():
                session.delete(user)
            session.commit()

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws/events?token={token}"):
                pass
        assert excinfo.value.code == 4401

    def test_websocket_closes_the_session_before_streaming(
        self, client, engine, monkeypatch
    ):
        # A WebSocket handler that holds a Session keeps a pooled connection
        # checked out for the life of the socket. Assert on Session.close: the
        # `engine` fixture uses StaticPool, which never reports a checkout count.
        closed: list[Session] = []
        real_close = Session.close

        def _record(self):
            closed.append(self)
            return real_close(self)

        monkeypatch.setattr(Session, "close", _record)
        token = _make_token(engine)

        with client.websocket_connect("/ws/events", subprotocols=[token]) as ws:
            assert closed, "session must be closed before the socket starts streaming"
            ws.send_text("ping")

    def test_websocket_accepts_token_as_subprotocol(self, client, engine):
        # The subprotocol is the only way to authenticate without putting the
        # JWT in the request line, which uvicorn writes to its access log.
        token = _make_token(engine)
        with client.websocket_connect("/ws/events", subprotocols=[token]) as ws:
            assert ws.accepted_subprotocol == token

    def test_query_token_still_accepted_for_older_clients(self, client, token):
        with client.websocket_connect(f"/ws/events?token={token}"):
            assert len(manager.active) == 1

    def test_invalid_subprotocol_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/events", subprotocols=["garbage"]):
                pass
        assert excinfo.value.code == 4401


class TestTenantScopedBroadcast:
    """A tenant's request logs must not reach another tenant's socket.

    The relay fans every `logs` event out to every connected client; the UI
    filter runs too late, after the host, path and client IP are already on the
    wire.
    """

    def _ws(self):
        return FakeWebSocket()

    async def test_member_only_receives_their_tenants_logs(self):
        m = type(manager)()
        scoped, other = self._ws(), self._ws()
        await m.connect(scoped, tenant_scope={1})
        await m.connect(other, tenant_scope={2})

        await m.broadcast("logs", {"tenant_id": 1, "id": 1})
        assert scoped.sent == [{"topic": "logs", "data": {"tenant_id": 1, "id": 1}}]
        assert other.sent == []

    async def test_admin_sees_every_tenant(self):
        m = type(manager)()
        admin = self._ws()
        await m.connect(admin, tenant_scope=None)

        await m.broadcast("logs", {"tenant_id": 1, "id": 1})
        await m.broadcast("logs", {"tenant_id": 2, "id": 2})
        assert [e["data"]["id"] for e in admin.sent] == [1, 2]

    async def test_unscoped_log_reaches_only_admins(self):
        m = type(manager)()
        admin, member = self._ws(), self._ws()
        await m.connect(admin, tenant_scope=None)
        await m.connect(member, tenant_scope={1})

        await m.broadcast("logs", {"tenant_id": None, "id": 1})
        assert [e["data"]["id"] for e in admin.sent] == [1]
        assert member.sent == []

    async def test_stats_are_scoped_to_the_members_tenants(self):
        # `stats` carries one tenant's counts; a member must not learn how
        # many proxies another tenant has.
        m = type(manager)()
        member, other, admin = self._ws(), self._ws(), self._ws()
        await m.connect(member, tenant_scope={1})
        await m.connect(other, tenant_scope={2})
        await m.connect(admin, tenant_scope=None)

        payload = {"tenant_id": 1, "total": 3, "alive": 2, "dead": 1, "unknown": 0}
        await m.broadcast("stats", payload)

        assert member.sent == [{"topic": "stats", "data": payload}]
        assert other.sent == []
        assert admin.sent == [{"topic": "stats", "data": payload}]

    async def test_unscoped_stats_reach_only_admins(self):
        m = type(manager)()
        admin, member = self._ws(), self._ws()
        await m.connect(admin, tenant_scope=None)
        await m.connect(member, tenant_scope={1})

        await m.broadcast("stats", {"tenant_id": None, "total": 1})
        assert len(admin.sent) == 1
        assert member.sent == []

    async def test_unknown_topics_are_not_filtered(self):
        # Only topics listed in SCOPED_TOPICS carry tenant data; a future
        # global notice (e.g. "settings changed") must reach every socket.
        m = type(manager)()
        member = self._ws()
        await m.connect(member, tenant_scope={1})
        await m.broadcast("notice", {"message": "restarting"})
        assert member.sent == [{"topic": "notice", "data": {"message": "restarting"}}]

    async def test_disconnect_drops_the_scope(self):
        m = type(manager)()
        ws = self._ws()
        await m.connect(ws, tenant_scope={1})
        m.disconnect(ws)
        assert m._tenant_scopes == {}


def test_websocket_scope_matches_memberships(client, engine):
    """A member connects with exactly their membership set, an admin with all."""
    from app.models.tenant import Tenant, TenantMembership

    with Session(engine) as session:
        tenant = Tenant(name="Acme", slug="acme")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        tenant_id = tenant.id

        member = User(
            username="scoped-member", hashed_password=hash_password("pw"), is_admin=False
        )
        session.add(member)
        session.commit()
        session.refresh(member)
        session.add(TenantMembership(tenant_id=tenant_id, user_id=member.id, role="member"))
        session.commit()
        member_token = create_access_token({"sub": str(member.id)})

        admin = User(
            username="scoped-admin", hashed_password=hash_password("pw"), is_admin=True
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        admin_token = create_access_token({"sub": str(admin.id)})

    with client.websocket_connect("/ws/events", subprotocols=[member_token]):
        assert manager._tenant_scopes[manager.active[-1]] == {tenant_id}

    with client.websocket_connect("/ws/events", subprotocols=[admin_token]):
        assert manager._tenant_scopes[manager.active[-1]] is None
