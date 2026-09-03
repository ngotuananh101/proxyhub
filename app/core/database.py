from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_db_and_tables(target_engine=None):
    db_engine = target_engine or engine
    SQLModel.metadata.create_all(db_engine)

    # Ensure tenant_id column exists on existing tables if migrated from pre-tenant schema
    from sqlalchemy import inspect, text

    inspector = inspect(db_engine)
    tables_to_patch = ["proxies", "proxysources", "requestlogs"]
    for table_name in tables_to_patch:
        if inspector.has_table(table_name):
            cols = {c["name"] for c in inspector.get_columns(table_name)}
            if "tenant_id" not in cols:
                with db_engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN tenant_id INTEGER"
                        )
                    )

    # Patch requestlogs with gateway auth columns if missing
    if inspector.has_table("requestlogs"):
        cols = {c["name"] for c in inspector.get_columns("requestlogs")}
        if "auth_credential_id" not in cols:
            with db_engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE requestlogs ADD COLUMN auth_credential_id INTEGER")
                )
        if "auth_status" not in cols:
            with db_engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE requestlogs ADD COLUMN auth_status VARCHAR")
                )


def get_session():
    with Session(engine) as session:
        yield session
