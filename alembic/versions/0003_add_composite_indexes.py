"""add composite indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

"""
from typing import Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index(
        "ix_gateway_credentials_auth_username_active",
        "gateway_credentials",
        ["auth_mode", "username", "is_active"],
    )
    op.create_index(
        "ix_proxies_tenant_status_scheme",
        "proxies",
        ["tenant_id", "status", "scheme"],
    )


def downgrade() -> None:
    op.drop_index("ix_proxies_tenant_status_scheme", table_name="proxies")
    op.drop_index("ix_gateway_credentials_auth_username_active", table_name="gateway_credentials")
