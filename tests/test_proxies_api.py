import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
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
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_proxy(client, auth_headers):
    resp = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["host"] == "1.2.3.4"
    assert data["status"] == "unknown"


def test_create_duplicate_proxy(client, auth_headers):
    body = {"scheme": "http", "host": "1.2.3.4", "port": 8080}
    client.post("/api/proxies", json=body, headers=auth_headers)
    resp = client.post("/api/proxies", json=body, headers=auth_headers)
    assert resp.status_code == 409


def test_list_proxies(client, auth_headers):
    client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.1.1.1", "port": 80},
        headers=auth_headers,
    )
    client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "2.2.2.2", "port": 80},
        headers=auth_headers,
    )
    resp = client.get("/api/proxies", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_proxies_status_filter_invalid(client, auth_headers):
    resp = client.get("/api/proxies?status=invalid_status", headers=auth_headers)
    assert resp.status_code == 422


def test_import_proxies(client, auth_headers):
    resp = client.post(
        "/api/proxies/import",
        json={"text": "http://1.1.1.1:80\nhttp://2.2.2.2:80\nbadline"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert len(data["invalid"]) == 1


def test_delete_proxy(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "9.9.9.9", "port": 80},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.delete(f"/api/proxies/{proxy_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_proxies_require_auth(client):
    resp = client.get("/api/proxies")
    assert resp.status_code == 401
