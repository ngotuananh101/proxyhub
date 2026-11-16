import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.core.database import _set_sqlite_pragma
from app.models.proxy import Proxy
from app.models.tenant import Tenant


@pytest.fixture(name="fk_engine")
def fk_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _set_sqlite_pragma)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_sqlite_enforces_foreign_keys(fk_engine):
    with Session(fk_engine) as session:
        assert session.exec(text("PRAGMA foreign_keys")).one()[0] == 1


def test_deleting_a_tenant_with_proxies_is_rejected(fk_engine):
    # Without PRAGMA foreign_keys=ON, SQLite silently leaves the proxies
    # orphaned and they keep showing up in no tenant at all.
    with Session(fk_engine) as session:
        tenant = Tenant(name="Acme", slug="acme-fk")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        session.add(
            Proxy(scheme="http", host="1.1.1.1", port=80, tenant_id=tenant.id)
        )
        session.commit()

        session.delete(tenant)
        with pytest.raises(IntegrityError):
            session.commit()
