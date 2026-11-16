"""Guards for the SQLite → PostgreSQL copy script.

The copy itself needs a live PostgreSQL; what can be checked here is the table
list (ordering matters for foreign keys) and the row-shape helpers.
"""
from datetime import datetime

from scripts.migrate_sqlite_to_postgres import TABLES, _fix_datetimes


def test_tables_cover_every_model_table():
    from sqlmodel import SQLModel

    import app.models  # noqa: F401  (register tables)

    assert set(TABLES) == set(SQLModel.metadata.tables)
    # No duplicates: the loop would otherwise insert a table twice, and the
    # second pass would be skipped as "already has rows" only by luck.
    assert len(TABLES) == len(set(TABLES))


def test_parent_tables_come_before_dependants():
    for parent in ("tenants", "users"):
        for child in ("tenant_memberships", "gateway_credentials", "proxies", "proxysources"):
            assert TABLES.index(parent) < TABLES.index(child)
    assert TABLES.index("gateway_credentials") < TABLES.index("requestlogs")


def test_fix_datetimes_attaches_utc():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    fixed = _fix_datetimes({"created_at": naive, "host": "1.2.3.4"})
    assert fixed["created_at"].tzinfo is not None
    assert fixed["created_at"].hour == 3
    assert fixed["host"] == "1.2.3.4"
