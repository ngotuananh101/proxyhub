# tests/test_integration.py
"""Integration test: full flow from API to internal proxy selection."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.proxy import Proxy, ProxyStatus
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="admin", hashed_password=hash_password("admin123"), is_admin=True)
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


def test_full_flow(client, auth_headers, engine):
    """Import proxies → verify stats → internal API returns a proxy."""
    # Import
    resp = client.post(
        "/api/proxies/import",
        json={"text": "http://10.0.0.1:8080\nhttp://10.0.0.2:8080"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    # Stats
    resp = client.get("/api/stats/summary", headers=auth_headers)
    assert resp.json()["total"] == 2
    assert resp.json()["unknown"] == 2

    # Internal API picks one
    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] in ("10.0.0.1", "10.0.0.2")
    assert data["port"] == 8080


def test_dead_proxy_excluded_from_internal(client, auth_headers, engine):
    """Mark all proxies dead → internal API returns 404."""
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="10.0.0.1", port=80, status=ProxyStatus.DEAD))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404
