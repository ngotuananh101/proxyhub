"""add tenants

Revision ID: 0001
Revises: 0000
Create Date: 2026-08-20

Every step is guarded by an existence check. A database bootstrapped by
`SQLModel.metadata.create_all` already has these tables, columns and indexes
but no alembic_version row; the baseline adopts it and this revision must then
patch it without trying to create what is already there.
"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = "0000"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_index(table: str, index: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index in {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    if not _has_table("tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not _has_index("tenants", "ix_tenants_slug"):
        op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    if not _has_table("tenant_memberships"):
        op.create_table(
            "tenant_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
        )
    if not _has_index("tenant_memberships", "ix_tenant_memberships_tenant_id"):
        op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    if not _has_index("tenant_memberships", "ix_tenant_memberships_user_id"):
        op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    for table in ("proxies", "proxysources", "requestlogs"):
        if not _has_table(table):
            continue
        if not _has_column(table, "tenant_id"):
            op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
        if not _has_index(table, f"ix_{table}_tenant_id"):
            op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_requestlogs_tenant_id", table_name="requestlogs")
    op.drop_column("requestlogs", "tenant_id")
    op.drop_index("ix_proxysources_tenant_id", table_name="proxysources")
    op.drop_column("proxysources", "tenant_id")
    op.drop_index("ix_proxies_tenant_id", table_name="proxies")
    op.drop_column("proxies", "tenant_id")
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
