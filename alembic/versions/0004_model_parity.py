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

Before the unique index can be created, duplicate (auth_mode, username) rows
have to be resolved: `create_all` never allowed them, but a database migrated
through 0003 could contain them because the global-uniqueness check was added
later. The gateway cannot disambiguate such a username, so the oldest
credential keeps it and the others are renamed to `<username>~<id>` and
disabled; an operator can then re-enable them under a fresh username.

SQLite cannot ALTER TABLE ... ADD CONSTRAINT, hence batch mode, which rebuilds
the table (on PostgreSQL batch mode emits the plain ALTER).
"""
import logging
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

logger = logging.getLogger("alembic.runtime.migration")

_UNIQUE_INDEX = "ix_gateway_credentials_auth_mode_username"
_UNIQUE_CONSTRAINT = "uq_proxy_tenant_scheme_host_port"


def _has_index(table: str, index: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index in {i["name"] for i in inspector.get_indexes(table)}


def _has_unique_constraint(table: str, columns: list[str]) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint["column_names"] == columns
        for constraint in inspector.get_unique_constraints(table)
    )


def _resolve_duplicate_usernames(bind: sa.Connection) -> int:
    """Rename and deactivate every credential but the oldest per (mode, username).

    Returns the number of rows changed.
    """
    duplicates = bind.execute(
        sa.text(
            """
            SELECT auth_mode, username, COUNT(*) AS n
            FROM gateway_credentials
            WHERE username IS NOT NULL
            GROUP BY auth_mode, username
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if not duplicates:
        return 0

    renamed = 0
    for auth_mode, username, _count in duplicates:
        rows = bind.execute(
            sa.text(
                """
                SELECT id FROM gateway_credentials
                WHERE auth_mode = :auth_mode AND username = :username
                ORDER BY created_at, id
                """
            ),
            {"auth_mode": auth_mode, "username": username},
        ).fetchall()
        for (cred_id,) in rows[1:]:
            bind.execute(
                sa.text(
                    """
                    UPDATE gateway_credentials
                    SET username = :username, is_active = false
                    WHERE id = :cred_id
                    """
                ),
                {"username": f"{username}~{cred_id}", "cred_id": cred_id},
            )
            renamed += 1
            logger.warning(
                "Renamed duplicate %s credential %s (%r -> %r) and disabled it; "
                "re-enable it under a fresh username",
                auth_mode,
                cred_id,
                username,
                f"{username}~{cred_id}",
            )
    return renamed


def upgrade() -> None:
    bind = op.get_bind()
    _resolve_duplicate_usernames(bind)

    if _has_index("gateway_credentials", "ix_gateway_credentials_auth_username_active"):
        op.drop_index(
            "ix_gateway_credentials_auth_username_active", table_name="gateway_credentials"
        )
    if not _has_index("gateway_credentials", _UNIQUE_INDEX):
        op.create_index(
            _UNIQUE_INDEX,
            "gateway_credentials",
            ["auth_mode", "username"],
            unique=True,
        )

    # 0000-0003 rebuild `proxies` several times on SQLite, and a batch rebuild
    # carries the constraint over once it exists, so check before adding it.
    if not _has_unique_constraint(
        "proxies", ["tenant_id", "scheme", "host", "port"]
    ):
        with op.batch_alter_table("proxies") as batch_op:
            batch_op.create_unique_constraint(
                _UNIQUE_CONSTRAINT,
                ["tenant_id", "scheme", "host", "port"],
            )


def downgrade() -> None:
    if _has_unique_constraint("proxies", ["tenant_id", "scheme", "host", "port"]):
        with op.batch_alter_table("proxies") as batch_op:
            batch_op.drop_constraint(_UNIQUE_CONSTRAINT, type_="unique")

    if _has_index("gateway_credentials", _UNIQUE_INDEX):
        op.drop_index(_UNIQUE_INDEX, table_name="gateway_credentials")
    if not _has_index("gateway_credentials", "ix_gateway_credentials_auth_username_active"):
        op.create_index(
            "ix_gateway_credentials_auth_username_active",
            "gateway_credentials",
            ["auth_mode", "username", "is_active"],
        )
