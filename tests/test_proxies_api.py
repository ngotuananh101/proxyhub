from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import hash_password
from app.models.proxy import Proxy, ProxyStatus
from app.models.tenant import Tenant
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
        tenant = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
        if tenant is None:
            tenant = Tenant(name="Default", slug="default")
            session.add(tenant)
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


def test_check_all_dispatches_task(client, auth_headers):
    mock_async_result = MagicMock()
    mock_async_result.id = "fake-task-id"
    with patch(
        "app.api.proxies.check_all_proxies.delay", return_value=mock_async_result
    ) as mock_delay:
        resp = client.post("/api/proxies/check-all", headers=auth_headers)
    assert resp.status_code == 202
    data = resp.json()
    assert data["detail"] == "Health check started"
    assert data["task_id"] == "fake-task-id"
    mock_delay.assert_called_once()


def test_check_all_requires_auth(client):
    resp = client.post("/api/proxies/check-all")
    assert resp.status_code == 401


def test_clear_dead_deletes_only_dead(client, auth_headers, engine):
    with Session(engine) as session:
        tenant = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE, tenant_id=tenant.id))
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.DEAD, tenant_id=tenant.id))
        session.add(Proxy(scheme="http", host="3.3.3.3", port=80, status=ProxyStatus.UNKNOWN, tenant_id=tenant.id))
        session.commit()

    resp = client.post("/api/proxies/clear-dead", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1}
    remaining = client.get("/api/proxies", headers=auth_headers).json()
    hosts = {item["host"] for item in remaining["items"]}
    assert hosts == {"1.1.1.1", "3.3.3.3"}


def test_clear_dead_requires_auth(client):
    resp = client.post("/api/proxies/clear-dead")
    assert resp.status_code == 401


def test_update_proxy_host(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"host": "5.6.7.8"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["host"] == "5.6.7.8"
    assert resp.json()["port"] == 8080  # unchanged


def test_update_proxy_scheme(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"scheme": "https"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["scheme"] == "https"


def test_update_proxy_status(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"status": "alive"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_update_proxy_invalid_scheme(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"scheme": "socks5"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_proxy_invalid_status(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"status": "bananas"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_proxy_duplicate_conflict(client, auth_headers):
    client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.1.1.1", "port": 80},
        headers=auth_headers,
    )
    create2 = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "2.2.2.2", "port": 80},
        headers=auth_headers,
    )
    proxy2_id = create2.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy2_id}",
        json={"host": "1.1.1.1"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_update_proxy_same_values_no_conflict(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"host": "1.2.3.4"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_update_proxy_not_found(client, auth_headers):
    resp = client.put(
        "/api/proxies/99999",
        json={"host": "1.1.1.1"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_update_proxy_port_out_of_range(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"port": 70000},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_proxy_port_valid(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"port": 9090},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["port"] == 9090

