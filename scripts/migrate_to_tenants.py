"""One-time: create default tenant and assign existing rows to it."""
import sys

from sqlmodel import Session, select

from app.core.database import engine
from app.models import Proxy, ProxySource, RequestLog, User
from app.models.tenant import TenantMembership
from app.services.tenant_service import ensure_default_tenant


def main() -> None:
    with Session(engine) as session:
        tenant = ensure_default_tenant(session)

        for model in (Proxy, ProxySource, RequestLog):
            rows = session.exec(select(model).where(model.tenant_id.is_(None))).all()
            for row in rows:
                row.tenant_id = tenant.id
                session.add(row)

        # Attach all existing users to the default tenant as admins
        users = session.exec(select(User)).all()
        for user in users:
            existing = session.exec(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            ).first()
            if existing is None:
                session.add(
                    TenantMembership(
                        tenant_id=tenant.id, user_id=user.id, role="admin"
                    )
                )

        session.commit()
        print(f"Migrated data to tenant '{tenant.slug}' (id={tenant.id})")


if __name__ == "__main__":
    sys.exit(main())
