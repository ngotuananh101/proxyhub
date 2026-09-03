import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.models.credential import AuthMode, GatewayCredential
from app.models.log import RequestLog
from app.models.tenant import Tenant
from app.schemas.credential import (
    GatewayCredentialCreate,
    GatewayCredentialResponse,
    GatewayCredentialUpdate,
)


def test_create_basic_credential_model(engine):
    with Session(engine) as session:
        tenant = Tenant(name="Test Tenant", slug="test-cred-tenant")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="test-basic",
            auth_mode=AuthMode.BASIC,
            username="bot1",
            password_hash="$2b$12$fakehashplaceholder",
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        assert cred.id is not None
        assert cred.tenant_id == tenant.id
        assert cred.auth_mode == "basic"
        assert cred.username == "bot1"
        assert cred.cidrs is None
        assert cred.is_active is True
        assert cred.last_used_at is None
        assert cred.created_at is not None


def test_create_ip_whitelist_credential_model(engine):
    with Session(engine) as session:
        tenant = Tenant(name="Test Tenant 2", slug="test-cred-tenant-2")
        session.add(tenant)
        session.commit()

        cred = GatewayCredential(
            tenant_id=tenant.id,
            name="test-ip",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.1.0/24,10.0.0.1/32",
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        assert cred.id is not None
        assert cred.auth_mode == "ip_whitelist"
        assert cred.username is None
        assert cred.password_hash is None
        assert "192.168.1.0/24" in cred.cidrs


def test_request_log_has_auth_fields(engine):
    with Session(engine) as session:
        log = RequestLog(
            client_ip="1.2.3.4",
            method="GET",
            host="example.com",
            auth_credential_id=42,
            auth_status="allowed",
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        assert log.auth_credential_id == 42
        assert log.auth_status == "allowed"


def test_schema_create_basic_validation():
    data = GatewayCredentialCreate(
        name="crawler",
        auth_mode="basic",
        username="user1",
    )
    assert data.auth_mode == "basic"
    assert data.username == "user1"


def test_schema_create_ip_whitelist_validation():
    data = GatewayCredentialCreate(
        name="office",
        auth_mode="ip_whitelist",
        cidrs="10.0.0.0/8, 192.168.1.1",
    )
    assert data.auth_mode == "ip_whitelist"


def test_schema_create_rejects_invalid_mode():
    with pytest.raises(ValidationError):
        GatewayCredentialCreate(name="bad", auth_mode="ldap")
