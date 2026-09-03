import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_access_token, hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def auth_headers(user: User, tenant_id: int | None = None) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = str(tenant_id)
    return headers


def test_list_credentials_requires_auth(client):
    resp = client.get("/api/gateway-credentials")
    assert resp.status_code == 401


def test_create_basic_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin1", email="a1@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 1", slug="t1-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "my-basic", "auth_mode": "basic", "username": "crawler1"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my-basic"
    assert data["auth_mode"] == "basic"
    assert data["username"] == "crawler1"
    assert "generated_password" in data
    assert len(data["generated_password"]) >= 16
    assert "password_hash" not in data


def test_create_duplicate_username_in_tenant_fails(client, engine):
    with Session(engine) as session:
        user = User(username="admin2", email="a2@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 2", slug="t2-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp1 = client.post(
        "/api/gateway-credentials",
        json={"name": "c1", "auth_mode": "basic", "username": "dup_user"},
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/gateway-credentials",
        json={"name": "c2", "auth_mode": "basic", "username": "dup_user"},
        headers=headers,
    )
    assert resp2.status_code == 409


def test_create_ip_whitelist_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin3", email="a3@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 3", slug="t3-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "office-net", "auth_mode": "ip_whitelist", "cidrs": "192.168.1.0/24, 10.0.0.1"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "office-net"
    assert data["auth_mode"] == "ip_whitelist"
    assert "192.168.1.0/24" in data["cidrs"]
    assert data["generated_password"] is None


def test_create_ip_whitelist_invalid_cidr_fails(client, engine):
    with Session(engine) as session:
        user = User(username="admin4", email="a4@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 4", slug="t4-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    resp = client.post(
        "/api/gateway-credentials",
        json={"name": "bad-net", "auth_mode": "ip_whitelist", "cidrs": "not-valid-cidr"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_rotate_password_returns_new_password_once(client, engine):
    with Session(engine) as session:
        user = User(username="admin5", email="a5@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 5", slug="t5-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "to-rotate", "auth_mode": "basic", "username": "rot_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]
    old_pw = create_resp.json()["generated_password"]

    patch_resp = client.patch(
        f"/api/gateway-credentials/{cred_id}",
        json={"rotate_password": True},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["generated_password"] is not None
    assert data["generated_password"] != old_pw


def test_toggle_active_status(client, engine):
    with Session(engine) as session:
        user = User(username="admin6", email="a6@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 6", slug="t6-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "toggle-me", "auth_mode": "basic", "username": "tog_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/gateway-credentials/{cred_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False


def test_delete_credential(client, engine):
    with Session(engine) as session:
        user = User(username="admin7", email="a7@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="Tenant 7", slug="t7-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

    headers = auth_headers(user, tenant.id)
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "to-del", "auth_mode": "basic", "username": "del_user"},
        headers=headers,
    )
    cred_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/gateway-credentials/{cred_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify gone from list
    list_resp = client.get("/api/gateway-credentials", headers=headers)
    assert not any(c["id"] == cred_id for c in list_resp.json()["items"])


def test_member_cannot_create_or_delete(client, engine):
    with Session(engine) as session:
        user = User(username="member1", email="m1@test.com", password_hash=hash_password("pw"), is_admin=False)
        session.add(user)
        tenant = Tenant(name="Tenant 8", slug="t8-crud")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

        membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=TenantRole.MEMBER)
        session.add(membership)
        session.commit()

    headers = auth_headers(user, tenant.id)

    # Member CAN list
    list_resp = client.get("/api/gateway-credentials", headers=headers)
    assert list_resp.status_code == 200

    # Member CANNOT create
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "forbidden", "auth_mode": "basic", "username": "forb"},
        headers=headers,
    )
    assert create_resp.status_code == 403
