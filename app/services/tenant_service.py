from sqlalchemy import text
from sqlmodel import Session, select

from app.models.tenant import Tenant, TenantMembership

DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"


def ensure_default_tenant(session: Session) -> Tenant:
    """Create and return the default tenant.

    Idempotent: also migrates any unassigned legacy rows (tenant_id is NULL)
    to the default tenant.
    """
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).first()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

    # Automatically assign legacy rows where tenant_id is NULL
    session.exec(
        text(f"UPDATE proxies SET tenant_id = {tenant.id} WHERE tenant_id IS NULL")
    )
    session.exec(
        text(f"UPDATE proxysources SET tenant_id = {tenant.id} WHERE tenant_id IS NULL")
    )
    session.exec(
        text(f"UPDATE requestlogs SET tenant_id = {tenant.id} WHERE tenant_id IS NULL")
    )
    session.commit()

    return tenant
