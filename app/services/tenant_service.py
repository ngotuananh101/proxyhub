from sqlmodel import Session, select

from app.models.tenant import Tenant

DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"


def ensure_default_tenant(session: Session) -> Tenant:
    """Create and return the default tenant. Idempotent."""
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).first()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
    return tenant
