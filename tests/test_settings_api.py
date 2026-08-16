import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import hash_password
from app.core.settings_registry import REGISTRY
from app.models.setting import AppSetting
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="admin", hashed_password=hash_password("admin123"), is_admin=True)
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="user_headers")
def user_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="member", hashed_password=hash_password("member123"))
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "member", "password": "member123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_settings_returns_all_registry_items(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {i["key"] for i in items} == set(REGISTRY.keys())
    for item in items:
        assert item["label"]
        assert item["type"] in ("string", "int", "float")
        assert item["value"] == REGISTRY[item["key"]].default


def test_get_settings_requires_auth(client):
    assert client.get("/api/settings").status_code in (401, 403)


def test_put_settings_updates_values(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"values": {"HEALTH_CHECK_TIMEOUT": "10", "HEALTH_CHECK_INTERVAL": "600"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    values = resp.json()["values"]
    assert values["HEALTH_CHECK_TIMEOUT"] == 10.0
    assert values["HEALTH_CHECK_INTERVAL"] == 600.0

    # Persisted and visible on the next GET
    items = client.get("/api/settings", headers=auth_headers).json()["items"]
    stored = {i["key"]: i["value"] for i in items}
    assert stored["HEALTH_CHECK_TIMEOUT"] == 10.0
    assert stored["HEALTH_CHECK_INTERVAL"] == 600.0


def test_put_settings_requires_admin(client, user_headers):
    resp = client.put(
        "/api/settings",
        json={"values": {"HEALTH_CHECK_TIMEOUT": "10"}},
        headers=user_headers,
    )
    assert resp.status_code == 403


def test_put_settings_requires_auth(client):
    resp = client.put("/api/settings", json={"values": {"HEALTH_CHECK_TIMEOUT": "10"}})
    assert resp.status_code in (401, 403)


def test_put_rejects_unknown_key(client, auth_headers):
    resp = client.put(
        "/api/settings", json={"values": {"NOT_A_SETTING": "1"}}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert "NOT_A_SETTING" in resp.json()["detail"]


def test_put_rejects_out_of_range(client, auth_headers):
    resp = client.put(
        "/api/settings", json={"values": {"HEALTH_CHECK_TIMEOUT": "0"}}, headers=auth_headers
    )
    assert resp.status_code == 400

    resp = client.put(
        "/api/settings",
        json={"values": {"HEALTH_CHECK_CONCURRENCY": "99999"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_put_rejects_wrong_type(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"values": {"HEALTH_CHECK_CONCURRENCY": "abc"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_put_rejects_empty_string(client, auth_headers):
    resp = client.put(
        "/api/settings", json={"values": {"HEALTH_CHECK_URL": "  "}}, headers=auth_headers
    )
    assert resp.status_code == 400


def test_seed_is_idempotent_and_preserves_overrides(engine, auth_headers, client):
    client.put(
        "/api/settings",
        json={"values": {"HEALTH_CHECK_TIMEOUT": "12"}},
        headers=auth_headers,
    )
    # A fresh app boot against the same DB must not reset stored values
    from app.main import create_app

    with TestClient(create_app(engine)) as c2:
        items = c2.get("/api/settings", headers=auth_headers).json()["items"]
    stored = {i["key"]: i["value"] for i in items}
    assert stored["HEALTH_CHECK_TIMEOUT"] == 12.0

    with Session(engine) as session:
        rows = session.exec(select(AppSetting)).all()
    assert len(rows) == len(REGISTRY)  # no duplicate rows
