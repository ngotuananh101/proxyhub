from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app) as c:
        yield c


def _login(client, engine, username, is_admin):
    with Session(engine) as session:
        session.add(
            User(username=username, hashed_password=hash_password("pass1234"), is_admin=is_admin)
        )
        session.commit()
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass1234"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(name="admin_headers")
def admin_headers_fixture(engine, client):
    return _login(client, engine, "admin", is_admin=True)


@pytest.fixture(name="user_headers")
def user_headers_fixture(engine, client):
    return _login(client, engine, "member", is_admin=False)


def test_startup_seeds_default_sources(client, admin_headers):
    resp = client.get("/api/sources", headers=admin_headers)
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert any(name.startswith("monosans/proxy-list") for name in names)
    assert any(name.startswith("TheSpeedX/PROXY-List") for name in names)


def test_list_requires_auth(client):
    assert client.get("/api/sources").status_code in (401, 403)


def test_create_source(client, admin_headers):
    resp = client.post(
        "/api/sources",
        json={
            "name": "My list",
            "url": "https://example.com/proxies.txt",
            "enabled": True,
            "interval_minutes": 30,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My list"
    assert data["interval_minutes"] == 30
    assert data["last_fetched_at"] is None


def test_create_requires_admin(client, user_headers):
    resp = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt"},
        headers=user_headers,
    )
    assert resp.status_code == 403


def test_create_rejects_non_http_url(client, admin_headers):
    resp = client.post(
        "/api/sources",
        json={"name": "x", "url": "ftp://example.com/p.txt"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_create_rejects_bad_interval(client, admin_headers):
    resp = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt", "interval_minutes": 0},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_update_source(client, admin_headers):
    created = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt"},
        headers=admin_headers,
    ).json()
    resp = client.put(
        f"/api/sources/{created['id']}",
        json={"enabled": False, "interval_minutes": 120},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["interval_minutes"] == 120
    assert data["name"] == "x"  # untouched fields preserved


def test_update_missing_source_404(client, admin_headers):
    resp = client.put("/api/sources/9999", json={"enabled": False}, headers=admin_headers)
    assert resp.status_code == 404


def test_delete_source(client, admin_headers):
    created = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt"},
        headers=admin_headers,
    ).json()
    resp = client.delete(f"/api/sources/{created['id']}", headers=admin_headers)
    assert resp.status_code == 204
    remaining = client.get("/api/sources", headers=admin_headers).json()
    assert created["id"] not in {s["id"] for s in remaining}


def test_delete_requires_admin(client, user_headers, admin_headers):
    created = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt"},
        headers=admin_headers,
    ).json()
    resp = client.delete(f"/api/sources/{created['id']}", headers=user_headers)
    assert resp.status_code == 403


def test_fetch_now_imports_proxies(client, admin_headers):
    created = client.post(
        "/api/sources",
        json={"name": "x", "url": "https://example.com/p.txt"},
        headers=admin_headers,
    ).json()

    with patch(
        "app.api.sources.fetch_and_import",
        return_value="ok: 5 imported, 0 duplicates",
    ) as mock_fetch:
        resp = client.post(f"/api/sources/{created['id']}/fetch", headers=admin_headers)

    assert resp.status_code == 202
    assert resp.json()["status"] == "ok: 5 imported, 0 duplicates"
    assert mock_fetch.call_count == 1
