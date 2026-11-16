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
    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "1.1.1.1"},
    )
    assert resp.status_code == 401


def test_internal_wrong_key(client):
    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "1.1.1.1"},
        headers={"X-Internal-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_internal_rejects_unknown_credentials(client):
    resp = client.post(
        "/internal/gateway/session",
        json={"username": "nobody", "password": "nope", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 401


def test_legacy_internal_proxies_endpoint_is_gone(client, engine):
    # The plugin switched to POST /internal/gateway/session; the old GET stayed
    # behind as a deprecated duplicate that skipped tenant scoping entirely.
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404
