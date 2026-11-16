"""add gateway credentials

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("auth_mode", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("cidrs", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_gateway_credentials_tenant_id", "gateway_credentials", ["tenant_id"])
    op.create_index("ix_gateway_credentials_auth_mode", "gateway_credentials", ["auth_mode"])
    op.create_index("ix_gateway_credentials_username", "gateway_credentials", ["username"])

    # SQLite cannot ALTER TABLE ... ADD CONSTRAINT, and this column carries a
    # foreign key; batch mode rebuilds the table so the FK lands on both
    # backends (on PostgreSQL batch mode emits the plain ALTER). Batch mode
    # requires the constraint to be named.
    with op.batch_alter_table("requestlogs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_credential_id",
                sa.Integer(),
                sa.ForeignKey(
                    "gateway_credentials.id",
                    name="fk_requestlogs_auth_credential_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
    op.create_index("ix_requestlogs_auth_credential_id", "requestlogs", ["auth_credential_id"])
    op.add_column("requestlogs", sa.Column("auth_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("requestlogs", "auth_status")
    op.drop_index("ix_requestlogs_auth_credential_id", table_name="requestlogs")
    # SQLite's DROP COLUMN refuses to drop a column a foreign key references,
    # so the table is rebuilt here too.
    with op.batch_alter_table("requestlogs") as batch_op:
        batch_op.drop_column("auth_credential_id")

    op.drop_index("ix_gateway_credentials_username", table_name="gateway_credentials")
    op.drop_index("ix_gateway_credentials_auth_mode", table_name="gateway_credentials")
    op.drop_index("ix_gateway_credentials_tenant_id", table_name="gateway_credentials")
    op.drop_table("gateway_credentials")
