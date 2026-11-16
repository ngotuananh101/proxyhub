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
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setattr(settings, "DB_URL", url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


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
