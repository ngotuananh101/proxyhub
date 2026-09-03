import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlmodel import Session, select

from app.core.database import create_db_and_tables
from app.models.source import ProxySource


def test_create_db_and_tables_adds_missing_tenant_id_columns():
    engine = create_engine("sqlite://")

    # Simulate legacy pre-tenant schema without tenant_id column
    meta = MetaData()
    Table(
        "proxysources",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String, nullable=False),
        Column("url", String, nullable=False),
        Column("enabled", Integer, default=1),
        Column("interval_minutes", Integer, default=60),
        Column("last_fetched_at", String, nullable=True),
        Column("last_status", String, nullable=True),
        Column("created_at", String, nullable=False),
    )
    Table(
        "proxies",
        meta,
        Column("id", Integer, primary_key=True),
        Column("scheme", String, nullable=False),
        Column("host", String, nullable=False),
        Column("port", Integer, nullable=False),
        Column("username", String, nullable=True),
        Column("password", String, nullable=True),
        Column("status", String, default="unknown"),
        Column("latency_ms", Integer, nullable=True),
        Column("last_checked_at", String, nullable=True),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
    )
    Table(
        "requestlogs",
        meta,
        Column("id", Integer, primary_key=True),
        Column("client_ip", String, nullable=True),
        Column("method", String, nullable=True),
        Column("host", String, nullable=True),
        Column("path", String, nullable=True),
        Column("proxy_host", String, nullable=True),
        Column("proxy_port", Integer, nullable=True),
        Column("response_bytes", Integer, nullable=True),
        Column("created_at", String, nullable=False),
    )
    meta.create_all(engine)

    # Verify tenant_id is missing initially
    inspector = inspect(engine)
    assert "tenant_id" not in [c["name"] for c in inspector.get_columns("proxysources")]
    assert "tenant_id" not in [c["name"] for c in inspector.get_columns("proxies")]
    assert "tenant_id" not in [c["name"] for c in inspector.get_columns("requestlogs")]

    # Run create_db_and_tables
    create_db_and_tables(target_engine=engine)

    # Verify tenant_id column was added
    inspector = inspect(engine)
    assert "tenant_id" in [c["name"] for c in inspector.get_columns("proxysources")]
    assert "tenant_id" in [c["name"] for c in inspector.get_columns("proxies")]
    assert "tenant_id" in [c["name"] for c in inspector.get_columns("requestlogs")]

    # Verify query works
    with Session(engine) as session:
        res = session.exec(select(ProxySource).where(ProxySource.tenant_id == 1)).all()
        assert res == []


def test_auto_patch_gateway_credentials(engine):
    create_db_and_tables(target_engine=engine)

    inspector = inspect(engine)
    assert inspector.has_table("gateway_credentials")

    log_cols = {c["name"] for c in inspector.get_columns("requestlogs")}
    assert "auth_credential_id" in log_cols
    assert "auth_status" in log_cols
