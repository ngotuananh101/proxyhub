"""baseline: pre-tenant schema

Revision ID: 0000
Revises:
Create Date: 2026-11-16

Bootstrap migration for an empty database. It recreates the schema as it stood
before the tenant work, so the existing migrations (0001 onward) apply
unchanged; 0004 then brings the result to parity with the current models.

For a database that already has the tables but no alembic_version row (every
deployment created with `create_all` before this baseline existed), upgrade()
adopts the existing tables instead of failing on the first CREATE TABLE.
"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0000"
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

BASELINE_TABLES = ["users", "appsettings", "proxies", "proxysources", "requestlogs"]


def upgrade() -> None:
    if set(BASELINE_TABLES).issubset(set(sa.inspect(op.get_bind()).get_table_names())):
        # Pre-Alembic database: the tables are already there (with or without
        # later columns), and the following revisions patch them in place.
        return

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        # The model declares email `unique=True` (a constraint) but username
        # `unique=True, index=True` (a unique index); the shapes differ and the
        # parity test compares them.
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "appsettings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
    )
    op.create_index("ix_appsettings_key", "appsettings", ["key"], unique=True)

    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheme", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("password", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=7), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_proxies_scheme", "proxies", ["scheme"])
    op.create_index("ix_proxies_host", "proxies", ["host"])
    op.create_index("ix_proxies_status", "proxies", ["status"])

    op.create_table(
        "proxysources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_proxysources_enabled", "proxysources", ["enabled"])

    op.create_table(
        "requestlogs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_ip", sa.String(), nullable=True),
        sa.Column("method", sa.String(), nullable=True),
        sa.Column("host", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("proxy_host", sa.String(), nullable=True),
        sa.Column("proxy_port", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_requestlogs_created_at", "requestlogs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_requestlogs_created_at", table_name="requestlogs")
    op.drop_table("requestlogs")
    op.drop_index("ix_proxysources_enabled", table_name="proxysources")
    op.drop_table("proxysources")
    op.drop_index("ix_proxies_status", table_name="proxies")
    op.drop_index("ix_proxies_host", table_name="proxies")
    op.drop_index("ix_proxies_scheme", table_name="proxies")
    op.drop_table("proxies")
    op.drop_index("ix_appsettings_key", table_name="appsettings")
    op.drop_table("appsettings")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
