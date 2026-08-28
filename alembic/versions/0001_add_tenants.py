"""add tenants

Revision ID: 0001
Revises:
Create Date: 2026-08-20

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.add_column("proxies", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_proxies_tenant_id", "proxies", ["tenant_id"])
    op.add_column("proxysources", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_proxysources_tenant_id", "proxysources", ["tenant_id"])
    op.add_column("requestlogs", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_requestlogs_tenant_id", "requestlogs", ["tenant_id"])


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
