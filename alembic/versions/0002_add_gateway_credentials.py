"""add gateway credentials

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29

Existence-guarded like 0001: a `create_all`-bootstrapped database already has
the table, the indexes and both requestlogs columns.
"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
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
    if not _has_table("gateway_credentials"):
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
    for index, columns in (
        ("ix_gateway_credentials_tenant_id", ["tenant_id"]),
        ("ix_gateway_credentials_auth_mode", ["auth_mode"]),
        ("ix_gateway_credentials_username", ["username"]),
    ):
        if not _has_index("gateway_credentials", index):
            op.create_index(index, "gateway_credentials", columns)

    if not _has_column("requestlogs", "auth_credential_id"):
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
    if not _has_index("requestlogs", "ix_requestlogs_auth_credential_id"):
        op.create_index("ix_requestlogs_auth_credential_id", "requestlogs", ["auth_credential_id"])
    if not _has_column("requestlogs", "auth_status"):
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
