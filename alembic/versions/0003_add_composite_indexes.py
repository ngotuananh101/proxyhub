"""add composite indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

Existence-guarded: `create_all` already declares
`ix_proxies_tenant_status_scheme` (on the model) and leaves
`ix_gateway_credentials_auth_username_active` absent, so a bootstrapped
database must only gain the latter.
"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _has_index(table: str, index: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index in {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    if not _has_index("gateway_credentials", "ix_gateway_credentials_auth_username_active"):
        op.create_index(
            "ix_gateway_credentials_auth_username_active",
            "gateway_credentials",
            ["auth_mode", "username", "is_active"],
        )
    if not _has_index("proxies", "ix_proxies_tenant_status_scheme"):
        op.create_index(
            "ix_proxies_tenant_status_scheme",
            "proxies",
            ["tenant_id", "status", "scheme"],
        )


def downgrade() -> None:
    op.drop_index("ix_proxies_tenant_status_scheme", table_name="proxies")
    op.drop_index("ix_gateway_credentials_auth_username_active", table_name="gateway_credentials")
