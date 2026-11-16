"""model parity: proxy uniqueness, credential username uniqueness

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16

Closes the drift between the migration chain and the SQLModel metadata:
  * proxies gain the (tenant, scheme, host, port) unique constraint the models
    declare, so duplicate imports are impossible under concurrency;
  * gateway_credentials gains a unique (auth_mode, username) index — the proxy
    sends no tenant context, so a basic-auth username must resolve to exactly
    one credential;
  * the older non-unique (auth_mode, username, is_active) index is dropped:
    it is a strict prefix of the new unique index and only cost writes.

SQLite cannot ALTER TABLE ... ADD CONSTRAINT, hence batch mode, which rebuilds
the table (on PostgreSQL batch mode emits the plain ALTER).
"""
from typing import Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_gateway_credentials_auth_username_active", table_name="gateway_credentials"
    )
    op.create_index(
        "ix_gateway_credentials_auth_mode_username",
        "gateway_credentials",
        ["auth_mode", "username"],
        unique=True,
    )

    with op.batch_alter_table("proxies") as batch_op:
        batch_op.create_unique_constraint(
            "uq_proxy_tenant_scheme_host_port",
            ["tenant_id", "scheme", "host", "port"],
        )


def downgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_constraint("uq_proxy_tenant_scheme_host_port", type_="unique")

    op.drop_index(
        "ix_gateway_credentials_auth_mode_username", table_name="gateway_credentials"
    )
    op.create_index(
        "ix_gateway_credentials_auth_username_active",
        "gateway_credentials",
        ["auth_mode", "username", "is_active"],
    )
