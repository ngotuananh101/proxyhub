"""Tests for the tenant + membership admin CRUD API."""
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


@pytest.fixture(name="admin_headers")
def admin_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            is_admin=True,
        )
        session.add(user)
        session.commit()
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="member_headers")
def member_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(
            username="member",
            hashed_password=hash_password("member123"),
            is_admin=False,
        )
        session.add(user)
        session.commit()
    resp = client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# -- Tenant tests -----------------------------------------------------------------


def test_create_tenant(client, admin_headers):
    resp = client.post("/api/tenants", json={"name": "Acme Corp"}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"


def test_create_tenant_with_explicit_slug(client, admin_headers):
    resp = client.post(
        "/api/tenants",
        json={"name": "Acme Corp", "slug": "acme-custom"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "acme-custom"


def test_list_tenants(client, admin_headers):
    client.post("/api/tenants", json={"name": "Acme Corp"}, headers=admin_headers)
    client.post(
        "/api/tenants",
        json={"name": "Beta LLC", "slug": "beta-llc"},
        headers=admin_headers,
    )
    resp = client.get("/api/tenants", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_create_duplicate_slug_conflict(client, admin_headers):
    client.post("/api/tenants", json={"name": "Acme Corp"}, headers=admin_headers)
    resp = client.post(
        "/api/tenants", json={"name": "Acme Corp"}, headers=admin_headers
    )
    assert resp.status_code == 409


def test_tenants_require_admin_access(client, member_headers):
    resp = client.get("/api/tenants", headers=member_headers)
    assert resp.status_code == 403


def test_create_tenant_requires_admin_access(client, member_headers):
    resp = client.post(
        "/api/tenants", json={"name": "Acme Corp"}, headers=member_headers
    )
    assert resp.status_code == 403


def test_tenants_require_auth(client):
    resp = client.get("/api/tenants")
    assert resp.status_code == 401


# -- Membership tests -------------------------------------------------------------


def _create_tenant(client, admin_headers):
    resp = client.post("/api/tenants", json={"name": "Acme Corp"}, headers=admin_headers)
    return resp.json()["id"]


def _create_user(engine, username):
    with Session(engine) as session:
        user = User(
            username=username,
            hashed_password=hash_password("pass123"),
            is_admin=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def test_list_members_empty(client, admin_headers):
    tenant_id = _create_tenant(client, admin_headers)
    resp = client.get(f"/api/tenants/{tenant_id}/members", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_member_admin_role(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    user_id = _create_user(engine, "target_admin")
    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "admin"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["role"] == "admin"
    assert data["tenant_id"] == tenant_id


def test_add_member_member_role(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    user_id = _create_user(engine, "target_member")
    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "member"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"


def test_add_member_default_role(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    user_id = _create_user(engine, "target_default")
    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"


def test_add_member_invalid_role(client, admin_headers):
    tenant_id = _create_tenant(client, admin_headers)
    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": 1, "role": "superadmin"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_add_member_tenant_not_found(client, admin_headers):
    resp = client.post(
        "/api/tenants/99999/members",
        json={"user_id": 1, "role": "member"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_add_member_duplicate_conflict(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    user_id = _create_user(engine, "target_dup")
    client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "member"},
        headers=admin_headers,
    )
    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "admin"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_remove_member(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    user_id = _create_user(engine, "target_remove")
    client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "member"},
        headers=admin_headers,
    )
    resp = client.delete(
        f"/api/tenants/{tenant_id}/members/{user_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 204


def test_remove_member_not_found(client, admin_headers, engine):
    tenant_id = _create_tenant(client, admin_headers)
    resp = client.delete(
        f"/api/tenants/{tenant_id}/members/99999",
        headers=admin_headers,
    )
    assert resp.status_code == 404
