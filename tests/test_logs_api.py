from datetime import datetime, timedelta, timezone
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


def _log(
    host: str,
    method: str = "GET",
    path: str = "/",
    client_ip: str = "1.1.1.1",
    proxy_host: str = "2.2.2.2",
    proxy_port: int = 8080,
    created_at: datetime | None = None,
):
    return RequestLog(
        method=method,
        host=host,
        path=path,
        client_ip=client_ip,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        created_at=created_at or datetime.now(timezone.utc),
    )


def _seed_logs(engine, logs: list[RequestLog]) -> None:
    with Session(engine) as session:
        for log in logs:
            session.add(log)
        session.commit()


class TestListLogs:
    def test_requires_auth(self, client):
        assert client.get("/api/logs").status_code == 401

    def test_returns_paginated_shape(self, client, auth_headers, engine):
        _seed_logs(engine, [_log(f"h{i}.example.com") for i in range(3)])

        resp = client.get("/api/logs", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"items", "total", "page", "size"}
        assert data["total"] == 3
        assert data["page"] == 1
        hosts = [log["host"] for log in data["items"]]
        assert hosts == ["h2.example.com", "h1.example.com", "h0.example.com"]

    def test_size_and_page_respected(self, client, auth_headers, engine):
        _seed_logs(engine, [_log(f"h{i}.example.com") for i in range(5)])

        resp = client.get("/api/logs?size=2&page=2", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 2
        assert len(data["items"]) == 2
        assert [log["host"] for log in data["items"]] == ["h2.example.com", "h1.example.com"]

    def test_method_filter_matches_exact(self, client, auth_headers, engine):
        _seed_logs(
            engine,
            [
                _log("a.example.com", method="GET"),
                _log("b.example.com", method="POST"),
                _log("c.example.com", method="CONNECT"),
            ],
        )

        resp = client.get("/api/logs?method=post", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["method"] == "POST"

    def test_q_matches_host_path_proxy_or_ip(self, client, auth_headers, engine):
        _seed_logs(
            engine,
            [
                _log("alpha.com", path="/home"),
                _log("beta.com", proxy_host="5.5.5.5"),
                _log("gamma.com", client_ip="9.9.9.9"),
                _log("delta.com"),
            ],
        )

        assert client.get("/api/logs?q=alp", headers=auth_headers).json()["total"] == 1
        assert client.get("/api/logs?q=/home", headers=auth_headers).json()["total"] == 1
        assert client.get("/api/logs?q=5.5.5", headers=auth_headers).json()["total"] == 1
        assert client.get("/api/logs?q=9.9.9", headers=auth_headers).json()["total"] == 1

    def test_start_end_filters_created_at(self, client, auth_headers, engine):
        now = datetime.now(timezone.utc)
        _seed_logs(
            engine,
            [
                _log("old.example.com", created_at=now - timedelta(days=10)),
                _log("mid.example.com", created_at=now - timedelta(days=5)),
                _log("new.example.com", created_at=now),
            ],
        )

        start = (now - timedelta(days=6)).isoformat()
        end = (now - timedelta(days=1)).isoformat()
        resp = client.get(
            "/api/logs", params={"start": start, "end": end}, headers=auth_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["host"] == "mid.example.com"

    def test_invalid_date_is_ignored(self, client, auth_headers, engine):
        _seed_logs(engine, [_log("a.example.com")])

        resp = client.get("/api/logs?start=not-a-date", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_size_out_of_bounds_rejected(self, client, auth_headers):
        assert client.get("/api/logs?size=0", headers=auth_headers).status_code == 422
        assert client.get("/api/logs?size=101", headers=auth_headers).status_code == 422
        assert client.get("/api/logs?page=0", headers=auth_headers).status_code == 422


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
