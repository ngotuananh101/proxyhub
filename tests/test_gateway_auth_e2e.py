import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import create_access_token, hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.log import RequestLog
from app.models.proxy import Proxy, ProxyStatus
from app.models.tenant import Tenant
from app.models.user import User

INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


def test_full_gateway_auth_lifecycle(client, engine):
    # 1. Setup tenant, admin user, alive proxy
    with Session(engine) as session:
        user = User(username="superadmin", email="sa@test.com", password_hash=hash_password("pw"), is_admin=True)
        session.add(user)
        tenant = Tenant(name="E2E Tenant", slug="e2e-tenant")
        session.add(tenant)
        session.commit()
        session.refresh(user)
        session.refresh(tenant)

        proxy = Proxy(
            tenant_id=tenant.id,
            scheme="http",
            host="192.168.99.1",
            port=8080,
            status=ProxyStatus.ALIVE,
        )
        session.add(proxy)
        session.commit()

    token = create_access_token({"sub": str(user.id)})
    api_headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(tenant.id)}

    # 2. Admin creates a Basic credential via CRUD API
    create_resp = client.post(
        "/api/gateway-credentials",
        json={"name": "e2e-bot", "auth_mode": "basic", "username": "e2e_crawler"},
        headers=api_headers,
    )
    assert create_resp.status_code == 201
    cred_data = create_resp.json()
    cred_id = cred_data["id"]
    password = cred_data["generated_password"]

    # 3. Client connects through gateway -> gateway calls session endpoint with wrong password
    fail_session = client.post(
        "/internal/gateway/session",
        json={"username": "e2e_crawler", "password": "wrong", "client_ip": "1.2.3.4"},
        headers=INTERNAL_HEADERS,
    )
    assert fail_session.status_code == 401

    # Gateway logs the denied attempt
    log_denied = client.post(
        "/internal/logs",
        json={
            "client_ip": "1.2.3.4",
            "method": "CONNECT",
            "host": "secret.com",
            "auth_status": "denied",
        },
        headers=INTERNAL_HEADERS,
    )
    assert log_denied.status_code == 201

    # 4. Client connects with correct password -> gateway calls session endpoint
    ok_session = client.post(
        "/internal/gateway/session",
        json={"username": "e2e_crawler", "password": password, "client_ip": "1.2.3.4"},
        headers=INTERNAL_HEADERS,
    )
    assert ok_session.status_code == 200
    session_data = ok_session.json()
    assert session_data["tenant_id"] == tenant.id
    assert session_data["credential_id"] == cred_id
    assert session_data["proxy"]["host"] == "192.168.99.1"

    # Gateway logs the allowed request
    log_allowed = client.post(
        "/internal/logs",
        json={
            "tenant_id": tenant.id,
            "auth_credential_id": cred_id,
            "auth_status": "allowed",
            "client_ip": "1.2.3.4",
            "method": "GET",
            "host": "api.ipify.org",
            "proxy_host": "192.168.99.1",
            "proxy_port": 8080,
            "response_bytes": 500,
        },
        headers=INTERNAL_HEADERS,
    )
    assert log_allowed.status_code == 201

    # 5. Verify request logs persisted correctly
    with Session(engine) as session:
        logs = session.exec(select(RequestLog).order_by(RequestLog.id.desc())).all()
        assert len(logs) >= 2
        allowed_row = logs[0]
        assert allowed_row.auth_status == "allowed"
        assert allowed_row.auth_credential_id == cred_id
        assert allowed_row.tenant_id == tenant.id

        denied_row = logs[1]
        assert denied_row.auth_status == "denied"
        assert denied_row.auth_credential_id is None
