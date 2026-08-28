from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.tenant import Tenant


def test_startup_seeds_default_tenant(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app):
        with Session(engine) as session:
            tenant = session.exec(
                select(Tenant).where(Tenant.slug == "default")
            ).first()
            assert tenant is not None
            assert tenant.name == "Default"
