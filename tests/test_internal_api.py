import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.proxy import Proxy, ProxyStatus


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


def test_internal_requires_key(client):
    resp = client.get("/internal/proxies")
    assert resp.status_code == 401


def test_internal_wrong_key(client):
    resp = client.get("/internal/proxies", headers={"X-Internal-Key": "wrong"})
    assert resp.status_code == 401


def test_internal_returns_proxy(client, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] == "1.1.1.1"
    assert data["port"] == 80


def test_internal_excludes_dead(client, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.DEAD))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404


def test_internal_invalid_strategy(client):
    resp = client.get("/internal/proxies?strategy=sticky", headers=INTERNAL_HEADERS)
    assert resp.status_code == 400
