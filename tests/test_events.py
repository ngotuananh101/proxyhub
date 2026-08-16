import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.testclient import WebSocketDisconnect

from app.core.security import hash_password
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


class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.accepted = False
        self.sent: list[dict] = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

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
