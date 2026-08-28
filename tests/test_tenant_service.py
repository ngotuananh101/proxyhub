from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.services.tenant_service import ensure_default_tenant


def test_create_tenant(session):
    tenant = Tenant(name="Acme", slug="acme")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    assert tenant.id is not None
    assert tenant.name == "Acme"
    assert tenant.slug == "acme"
    assert tenant.created_at is not None


def test_tenant_slug_unique(session):
    t1 = Tenant(name="Acme", slug="acme")
    session.add(t1)
    session.commit()

    t2 = Tenant(name="Acme2", slug="acme")
    session.add(t2)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()


def test_create_tenant_membership(session):
    tenant = Tenant(name="Default", slug="default")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    membership = TenantMembership(
        tenant_id=tenant.id, user_id=1, role=TenantRole.ADMIN
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    assert membership.id is not None
    assert membership.tenant_id == tenant.id
    assert membership.user_id == 1
    assert membership.role == TenantRole.ADMIN


def test_tenant_membership_default_role(session):
    tenant = Tenant(name="Default", slug="default")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    membership = TenantMembership(tenant_id=tenant.id, user_id=1)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    assert membership.role == TenantRole.MEMBER


def test_ensure_default_tenant_creates(session):
    tenant = ensure_default_tenant(session)
    assert tenant.id is not None
    assert tenant.name == "Default"
    assert tenant.slug == "default"


def test_ensure_default_tenant_idempotent(session):
    first = ensure_default_tenant(session)
    second = ensure_default_tenant(session)
    assert first.id == second.id
    assert second.name == "Default"
    assert second.slug == "default"


def test_ensure_default_tenant_migrates_null_tenant_rows(session):
    from app.models.proxy import Proxy
    from app.models.source import ProxySource

    p = Proxy(scheme="http", host="8.8.8.8", port=8080, tenant_id=None)
    s = ProxySource(name="Test Source", url="http://example.com/proxies.txt", tenant_id=None)
    session.add(p)
    session.add(s)
    session.commit()
    session.refresh(p)
    session.refresh(s)
    assert p.tenant_id is None
    assert s.tenant_id is None

    default_tenant = ensure_default_tenant(session)
    session.refresh(p)
    session.refresh(s)

    assert p.tenant_id == default_tenant.id
    assert s.tenant_id == default_tenant.id

