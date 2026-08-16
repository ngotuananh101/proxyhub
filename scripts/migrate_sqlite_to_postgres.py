"""One-shot migration of ProxyHub data from SQLite to PostgreSQL.

Usage (stop the app first so the SQLite file is not being written to):

    venv\\Scripts\\python -m scripts.migrate_sqlite_to_postgres [path/to/proxyhub.db]

DATABASE_URL must point at PostgreSQL (taken from the environment / .env).
Tables are created if missing; a table that already has rows is skipped,
so the script is safe to re-run.
"""

import sys
from datetime import datetime, timezone

from sqlalchemy import MetaData, create_engine, func, select, text
from sqlmodel import SQLModel

import app.models  # noqa: F401  (register tables on SQLModel.metadata)

TABLES = ["users", "appsettings", "proxies", "proxysources", "requestlogs"]
BATCH_SIZE = 1000


def _fix_datetimes(row: dict) -> dict:
    """SQLite hands datetimes back without their UTC offset; re-attach it."""
    return {
        k: (v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) and v.tzinfo is None else v)
        for k, v in row.items()
    }


def migrate(sqlite_url: str, pg_url: str) -> None:
    src = create_engine(sqlite_url)
    dst = create_engine(pg_url)

    src_meta = MetaData()
    src_meta.reflect(bind=src)

    SQLModel.metadata.create_all(dst)

    with dst.begin() as conn:
        for name in TABLES:
            if name not in src_meta.tables:
                print(f"  {name}: not present in SQLite file, skipped")
                continue

            dst_table = SQLModel.metadata.tables[name]
            existing = conn.execute(select(func.count()).select_from(dst_table)).scalar()
            if existing:
                print(f"  {name}: already has {existing} rows, skipped")
                continue

            src_table = src_meta.tables[name]
            with src.connect() as sconn:
                rows = [_fix_datetimes(dict(r._mapping)) for r in sconn.execute(select(src_table))]
            if not rows:
                print(f"  {name}: 0 rows")
                continue

            for i in range(0, len(rows), BATCH_SIZE):
                conn.execute(dst_table.insert(), rows[i : i + BATCH_SIZE])

            # Explicit ids were inserted, so advance the id sequence past them.
            max_id = max(r["id"] for r in rows)
            seq = conn.execute(
                text(f"SELECT pg_get_serial_sequence('{name}', 'id')")
            ).scalar()
            if seq:
                conn.execute(
                    text("SELECT setval(:seq, :max_id, true)"),
                    {"seq": seq, "max_id": max_id},
                )
            print(f"  {name}: {len(rows)} rows migrated")

    src.dispose()
    dst.dispose()
    print("Done.")


def main() -> None:
    from app.core.config import settings

    if settings.DATABASE_URL.startswith("sqlite"):
        sys.exit("DATABASE_URL still points at SQLite; set it to a PostgreSQL URL first.")

    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else "./proxyhub.db"
    print(f"Migrating {sqlite_path} -> {settings.DATABASE_URL.split('@')[-1]}")
    migrate(f"sqlite:///{sqlite_path}", settings.DATABASE_URL)


if __name__ == "__main__":
    main()
