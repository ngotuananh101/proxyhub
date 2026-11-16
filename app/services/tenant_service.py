from sqlalchemy import text
from sqlmodel import Session, select

from app.models.tenant import Tenant

DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"

# Legacy tables that gained a tenant_id column after the first release. Rows
# created before that migration have tenant_id IS NULL and are adopted by the
# default tenant.
LEGACY_TABLES = ("proxies", "proxysources", "requestlogs")


def ensure_default_tenant(session: Session) -> Tenant:
    """Create and return the default tenant.

    Idempotent and safe to call on every request: the tenant lookup is one
    indexed SELECT and the legacy-row adoption only issues UPDATEs when a row
    with a NULL tenant_id actually exists.
    """
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).first()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

    # Adopt legacy rows. On a database that has already been migrated this
    # costs one indexed SELECT per table; the unconditional UPDATEs this
    # replaces rewrote every row on every API request.
    changed = False
    for table in LEGACY_TABLES:
        unassigned = session.exec(
            text(f"SELECT 1 FROM {table} WHERE tenant_id IS NULL LIMIT 1")
        ).first()
        if unassigned is None:
            continue
        session.exec(
            text(f"UPDATE {table} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            params={"tenant_id": tenant.id},
        )
        changed = True

    if changed:
        session.commit()

    return tenant
