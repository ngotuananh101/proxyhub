from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.proxy import Proxy, ProxyStatus
from app.models.tenant import Tenant
from app.services.gateway_auth_service import clear_auth_cache

INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def test_session_requires_internal_key(client):
    resp = client.post("/internal/gateway/session", json={"client_ip": "1.2.3.4"})
    assert resp.status_code == 401


def test_session_wrong_internal_key(client):
    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "1.2.3.4"},
        headers={"X-Internal-Key": "bad-key"},
    )
    assert resp.status_code == 401


def test_session_basic_auth_success(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot",
            auth_mode=AuthMode.BASIC,
            username="bot_user",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
        session.add(cred)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="10.20.30.40",
            port=8080,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_user", "password": "secret123", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == tenant.id
    assert data["credential_id"] == cred.id
    assert data["auth_mode"] == "basic"
    assert data["proxy"]["host"] == "10.20.30.40"
    assert data["proxy"]["port"] == 8080
    assert "default_target_url" in data

    # Verify last_used_at was updated
    with Session(engine) as session:
        updated_cred = session.get(GatewayCredential, cred.id)
        assert updated_cred.last_used_at is not None


def test_session_basic_auth_invalid_password_returns_401(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant B", slug="tenant-b")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot",
            auth_mode=AuthMode.BASIC,
            username="bot_user_2",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_user_2", "password": "wrong_password", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_session_ip_whitelist_success(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant C", slug="tenant-c")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="office-ip",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.10.0/24",
            is_active=True,
        )
        session.add(cred)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="10.20.30.50",
            port=3128,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"client_ip": "192.168.10.99"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == tenant.id
    assert data["auth_mode"] == "ip_whitelist"
    assert data["proxy"]["host"] == "10.20.30.50"


def test_session_no_available_proxy_returns_404(client, engine):
    clear_auth_cache()
    with Session(engine) as session:
        tenant = Tenant(name="Tenant D", slug="tenant-d")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="bot_no_proxy",
            auth_mode=AuthMode.BASIC,
            username="bot_empty",
            password_hash=hash_password("pass"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

    resp = client.post(
        "/internal/gateway/session",
        json={"username": "bot_empty", "password": "pass", "client_ip": "1.1.1.1"},
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No available proxy"


def test_log_entry_accepts_auth_fields(client, engine):
    resp = client.post(
        "/internal/logs",
        json={
            "client_ip": "1.2.3.4",
            "method": "CONNECT",
            "host": "google.com",
            "tenant_id": 1,
            "auth_credential_id": 7,
            "auth_status": "allowed",
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["auth_status"] == "allowed"
    assert data["auth_credential_id"] == 7
