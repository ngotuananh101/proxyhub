from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import hash_password
from app.models.log import RequestLog
from app.models.user import User

INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_broadcast(monkeypatch):
    """Keep log ingest off a real Redis; tests assert on this mock."""
    fake = MagicMock()
    monkeypatch.setattr("app.api.internal.broadcast_sync", fake)
    return fake


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        session.add(User(username="loguser", hashed_password=hash_password("logpass123")))
        session.commit()
    resp = client.post(
        "/api/auth/login", json={"username": "loguser", "password": "logpass123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_logs(engine, n: int) -> None:
    with Session(engine) as session:
        for i in range(n):
            session.add(RequestLog(method="GET", host=f"h{i}.example.com", path="/"))
        session.commit()


class TestListLogs:
    def test_requires_auth(self, client):
        assert client.get("/api/logs").status_code == 401

    def test_returns_newest_first(self, client, auth_headers, engine):
        _seed_logs(engine, 3)

        resp = client.get("/api/logs", headers=auth_headers)

        assert resp.status_code == 200
        hosts = [log["host"] for log in resp.json()]
        assert hosts == ["h2.example.com", "h1.example.com", "h0.example.com"]

    def test_limit_respected(self, client, auth_headers, engine):
        _seed_logs(engine, 5)

        resp = client.get("/api/logs?limit=2", headers=auth_headers)

        assert len(resp.json()) == 2

    def test_limit_out_of_bounds_rejected(self, client, auth_headers):
        assert client.get("/api/logs?limit=0", headers=auth_headers).status_code == 422
        assert client.get("/api/logs?limit=501", headers=auth_headers).status_code == 422


class TestInternalLogIngest:
    def test_requires_key(self, client):
        assert client.post("/internal/logs", json={}).status_code == 401

    def test_wrong_key_rejected(self, client):
        resp = client.post("/internal/logs", json={}, headers={"X-Internal-Key": "wrong"})
        assert resp.status_code == 401

    def test_persists_and_broadcasts(self, client, engine, _no_broadcast):
        body = {
            "client_ip": "127.0.0.1",
            "method": "GET",
            "host": "httpbin.org",
            "path": "/ip",
            "proxy_host": "1.2.3.4",
            "proxy_port": 8080,
            "response_bytes": 512,
        }
        resp = client.post("/internal/logs", json=body, headers=INTERNAL_HEADERS)

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["host"] == "httpbin.org"
        assert data["created_at"]

        with Session(engine) as session:
            logs = session.exec(select(RequestLog)).all()
        assert len(logs) == 1
        assert logs[0].proxy_port == 8080

        _no_broadcast.assert_called_once()
        topic, payload = _no_broadcast.call_args.args
        assert topic == "logs"
        assert payload["id"] == data["id"]
        assert payload["host"] == "httpbin.org"

    def test_accepts_partial_body(self, client, _no_broadcast):
        resp = client.post(
            "/internal/logs", json={"host": "example.com"}, headers=INTERNAL_HEADERS
        )

        assert resp.status_code == 201
        assert resp.json()["host"] == "example.com"
        assert resp.json()["method"] is None
