"""The Alembic chain must reproduce exactly the schema the models describe.

The app still bootstraps with `SQLModel.metadata.create_all`, so a fresh
`alembic upgrade head` and a fresh `create_all` have to agree — otherwise a
deployment's schema depends on which of the two ran first.
"""
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from alembic import command
from app.core.config import settings

# Tables that exist today. alembic_version is bookkeeping, not schema.
TABLES = [
    "users",
    "appsettings",
    "proxies",
    "proxysources",
    "requestlogs",
    "tenants",
    "tenant_memberships",
    "gateway_credentials",
]


@pytest.fixture(name="migrated_url")
def migrated_url_fixture(tmp_path, monkeypatch):
    url = _point_settings_at(monkeypatch, tmp_path / "migrated.db")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


def _point_settings_at(monkeypatch, path) -> str:
    """Point alembic (and anything else reading settings) at one SQLite file.

    `env.py` derives its URL from settings via `build_db_url`, which ignores
    the config's `sqlalchemy.url`, so the discrete DB_* fields are what a test
    has to override.
    """
    monkeypatch.setattr(settings, "DB_CONNECTION", "sqlite")
    monkeypatch.setattr(settings, "DB_DATABASE", str(path))
    return f"sqlite:///{path}"


def _type_name(column_type) -> str:
    # VARCHAR vs VARCHAR(7) is a rendering difference, not a schema difference;
    # the storage class (and therefore the semantics) is the same.
    return type(column_type).__name__.upper()


def _introspect(engine) -> dict:
    inspector = inspect(engine)
    schema = {}
    for table in TABLES:
        if not inspector.has_table(table):
            schema[table] = None
            continue
        schema[table] = {
            "columns": {
                column["name"]: {
                    "type": _type_name(column["type"]),
                    "nullable": column["nullable"],
                }
                for column in inspector.get_columns(table)
            },
            "indexes": {
                (index["name"], tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table)
            },
            # Unique constraints may be anonymous (SQLite autoindexes), so
            # compare what they cover rather than what they are called.
            "unique": {
                tuple(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table)
            },
        }
    return schema


def _create_all_schema() -> dict:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        return _introspect(engine)
    finally:
        engine.dispose()


def test_alembic_head_matches_sqlmodel_metadata(migrated_url):
    engine = create_engine(migrated_url)
    try:
        migrated = _introspect(engine)
    finally:
        engine.dispose()

    expected = _create_all_schema()
    for table in TABLES:
        assert migrated[table] is not None, f"{table} was not created by alembic"
        assert migrated[table] == expected[table], f"schema drift in {table}"


def test_migrated_database_has_no_alembic_leftovers(migrated_url):
    engine = create_engine(migrated_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    # Every model table plus alembic's own version bookkeeping; nothing else.
    assert tables == set(TABLES) | {"alembic_version"}


def test_downgrade_to_base_drops_everything(migrated_url, monkeypatch):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", migrated_url)
    command.downgrade(config, "base")

    engine = create_engine(migrated_url)
    try:
        remaining = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert remaining == {"alembic_version"}


def test_upgrade_on_create_all_database(tmp_path, monkeypatch):
    """`create_all` then `alembic upgrade head` must work.

    Every deployment so far was bootstrapped by `create_all` (the lifespan
    calls it, docker-compose never runs alembic), so adopting such a database
    is the normal case, not an edge case. The chain must add only what is
    missing instead of failing on the first CREATE TABLE.
    """
    url = _point_settings_at(monkeypatch, tmp_path / "bootstrapped.db")
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        migrated = _introspect(engine)
    finally:
        engine.dispose()
    expected = _create_all_schema()
    assert migrated == expected


def test_upgrade_resolves_duplicate_credential_usernames(tmp_path, monkeypatch):
    """0004 must not abort when two tenants already share a basic username.

    The global-uniqueness check was added after credentials could be created,
    so a migrated database can hold duplicates. The gateway cannot tell them
    apart, so the older one keeps the username and the rest are renamed and
    disabled rather than dropping the whole upgrade.
    """
    from sqlalchemy import text

    url = _point_settings_at(monkeypatch, tmp_path / "duplicates.db")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0003")

    engine = create_engine(url)
    with engine.begin() as conn:
        tenant_ids = [
            conn.execute(
                text(
                    "INSERT INTO tenants (name, slug, created_at) "
                    "VALUES (:n, :n, '2026-01-01 00:00:00')"
                ),
                {"n": slug},
            ).lastrowid
            for slug in ("acme", "globex")
        ]
        for tenant_id in tenant_ids:
            conn.execute(
                text(
                    "INSERT INTO gateway_credentials "
                    "(tenant_id, name, auth_mode, username, password_hash, cidrs, "
                    "is_active, created_at) VALUES "
                    "(:t, 'cred', 'basic', 'shared', 'h', NULL, 1, "
                    "'2026-01-01 00:00:00')"
                ),
                {"t": tenant_id},
            )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT tenant_id, username, is_active FROM gateway_credentials "
                    "ORDER BY id"
                )
            ).fetchall()
            unique_index = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND name='ix_gateway_credentials_auth_mode_username'"
                )
            ).fetchall()
    finally:
        engine.dispose()

    assert rows[0] == (1, "shared", 1)
    assert rows[1][1] == "shared~2"
    assert rows[1][2] in (0, False)  # SQLite stores the boolean as 0
    assert unique_index, "the unique index must still be created"

