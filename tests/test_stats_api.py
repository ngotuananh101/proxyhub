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


def test_stats_summary(client, auth_headers, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE))
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.DEAD))
        session.add(Proxy(scheme="http", host="3.3.3.3", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()

    resp = client.get("/api/stats/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["alive"] == 1
    assert data["dead"] == 1
    assert data["unknown"] == 1
