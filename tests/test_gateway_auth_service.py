import time
from unittest.mock import patch
import pytest
from sqlmodel import Session

from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import Tenant
from app.services.gateway_auth_service import (
    authenticate_gateway_request,
    clear_auth_cache,
    ip_matches_cidrs,
    validate_cidrs,
    verify_credential_password,
)


def test_validate_cidrs_valid():
    result = validate_cidrs("192.168.1.0/24, 10.0.0.1, 2001:db8::/32")
    parts = [p.strip() for p in result.split(",")]
    assert "192.168.1.0/24" in parts
    assert "10.0.0.1/32" in parts  # normalized to /32
    assert "2001:db8::/32" in parts


def test_validate_cidrs_invalid():
    with pytest.raises(ValueError, match="Invalid CIDR"):
        validate_cidrs("not-an-ip")

    with pytest.raises(ValueError, match="Invalid CIDR"):
        validate_cidrs("999.999.999.999")


def test_validate_cidrs_rejects_exceeding_max_limit():
    from app.services.gateway_auth_service import MAX_CIDRS_PER_CREDENTIAL
    too_many = ",".join([f"10.0.{i // 256}.{i % 256}" for i in range(MAX_CIDRS_PER_CREDENTIAL + 10)])
    with pytest.raises(ValueError, match="Too many CIDRs"):
        validate_cidrs(too_many)


def test_validate_cidrs_empty():
    assert validate_cidrs("") == ""
    assert validate_cidrs("   ") == ""


def test_ip_matches_cidrs():
    cidrs = "192.168.1.0/24, 10.0.0.1/32"
    assert ip_matches_cidrs("192.168.1.55", cidrs) is True
    assert ip_matches_cidrs("10.0.0.1", cidrs) is True
    assert ip_matches_cidrs("10.0.0.2", cidrs) is False
    assert ip_matches_cidrs("8.8.8.8", cidrs) is False
    assert ip_matches_cidrs("invalid-ip", cidrs) is False
    assert ip_matches_cidrs("192.168.1.1", None) is False
    assert ip_matches_cidrs("192.168.1.1", "") is False
    # Test IPv4-mapped IPv6
    assert ip_matches_cidrs("::ffff:192.168.1.55", cidrs) is True


def test_bcrypt_cache_avoids_rehash(engine):
    clear_auth_cache()
    pw = "secret123"
    pw_hash = hash_password(pw)

    cred = GatewayCredential(
        id=1,
        tenant_id=1,
        name="test",
        auth_mode="basic",
        username="u1",
        password_hash=pw_hash,
    )

    # First call: hits bcrypt
    assert verify_credential_password(cred, pw) is True

    # Second call: hits cache (mock bcrypt to verify it's not called)
    with patch("app.services.gateway_auth_service.verify_password") as mock_verify:
        assert verify_credential_password(cred, pw) is True
        mock_verify.assert_not_called()

    # Wrong password: does not hit cache for correct password
    assert verify_credential_password(cred, "wrong") is False


def test_bcrypt_cache_ttl_expiry(engine):
    clear_auth_cache()
    pw = "secret123"
    pw_hash = hash_password(pw)

    cred = GatewayCredential(
        id=2,
        tenant_id=1,
        name="test",
        auth_mode="basic",
        username="u2",
        password_hash=pw_hash,
    )

    assert verify_credential_password(cred, pw) is True

    # Fast-forward time past TTL using mock
    with patch("app.services.gateway_auth_service.time.time", return_value=time.time() + 100):
        with patch("app.services.gateway_auth_service.verify_password", return_value=True) as mock_verify:
            assert verify_credential_password(cred, pw) is True
            mock_verify.assert_called_once()


def test_authenticate_basic_happy_path(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T1", slug="t1-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="basic-cred",
            auth_mode=AuthMode.BASIC,
            username="client1",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="client1",
            password="pass123",
            client_ip="1.2.3.4",
        )
        assert matched is not None
        assert matched.id == cred.id
        assert matched.tenant_id == t.id


def test_authenticate_basic_wrong_password(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T2", slug="t2-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="basic-cred2",
            auth_mode=AuthMode.BASIC,
            username="client2",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="client2",
            password="wrongpassword",
            client_ip="1.2.3.4",
        )
        assert matched is None


def test_authenticate_ip_whitelist_fallback(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T3", slug="t3-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="whitelist-cred",
            auth_mode=AuthMode.IP_WHITELIST,
            cidrs="192.168.100.0/24",
            is_active=True,
        )
        session.add(cred)
        session.commit()

        # Request without basic auth but matching IP
        matched = authenticate_gateway_request(
            session=session,
            username=None,
            password=None,
            client_ip="192.168.100.42",
        )
        assert matched is not None
        assert matched.id == cred.id


def test_authenticate_inactive_credential_ignored(engine):
    clear_auth_cache()
    with Session(engine) as session:
        t = Tenant(name="T4", slug="t4-auth")
        session.add(t)
        session.commit()

        cred = GatewayCredential(
            tenant_id=t.id,
            name="inactive-cred",
            auth_mode=AuthMode.BASIC,
            username="inactive_user",
            password_hash=hash_password("pass123"),
            is_active=False,
        )
        session.add(cred)
        session.commit()

        matched = authenticate_gateway_request(
            session=session,
            username="inactive_user",
            password="pass123",
            client_ip="1.2.3.4",
        )
        assert matched is None
