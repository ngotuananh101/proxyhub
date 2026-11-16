# tests/test_compose.py
"""Static checks on the Docker Compose files.

The default stack runs the bundled ``postgres`` and ``redis`` services. To
deploy against external services (e.g. Aiven) we layer
``docker-compose.external.yml`` on top with ``-f``; these tests pin the
contract that makes that layering work:

* the base ``app.environment`` is a mapping, so an override can replace
  single keys (a list would be appended, not merged per key);
* the base keeps the bundled defaults, so plain ``docker compose up`` is
  unchanged;
* the external override reads the DB/queue settings from ``.env`` instead
  of the hard-coded service names, drops the bundled ``depends_on``, and
  parks the bundled services behind a profile so they are not started.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = REPO_ROOT / "docker-compose.yml"
EXTERNAL_COMPOSE = REPO_ROOT / "docker-compose.external.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


class _ResetMarker:
    """Sentinel for a value removed with the compose ``!reset`` tag."""

    def __repr__(self):  # pragma: no cover - debugging aid
        return "!reset"


RESET = _ResetMarker()


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that understands compose's ``!reset`` / ``!override`` tags."""


def _construct_reset(loader, node):
    return RESET


def _construct_override(loader, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_constructor("!reset", _construct_reset)
_ComposeLoader.add_constructor("!override", _construct_override)


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)


def _env(service: dict) -> dict:
    """Return a service's environment as a plain dict (list or mapping form)."""
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return dict(raw)
    env = {}
    for item in raw:
        key, _, value = str(item).partition("=")
        env[key] = value
    return env


# --- base file: bundled defaults stay the default ----------------------------


def test_base_app_environment_is_a_mapping():
    # A mapping lets a layered override replace single keys; a list is only
    # appended, so the hard-coded bundled host would win over the override.
    app = _load(BASE_COMPOSE)["services"]["app"]
    assert isinstance(app["environment"], dict)


def test_base_app_defaults_to_bundled_services():
    env = _env(_load(BASE_COMPOSE)["services"]["app"])
    assert env["DB_CONNECTION"] == "postgresql"
    assert env["DB_HOST"] == "postgres"
    assert env["DB_PORT"] == "5432"
    assert "redis:6379" in env["QUEUE_BROKER_URL"]
    assert "redis:6379" in env["QUEUE_RESULT_BACKEND"]


def test_base_app_clears_db_sslmode_for_bundled_postgres():
    # .env may hold an external DB_SSLMODE (e.g. require for Aiven); the
    # bundled postgres does not speak TLS, so the base must blank it out.
    env = _env(_load(BASE_COMPOSE)["services"]["app"])
    assert env["DB_SSLMODE"] == ""


def test_base_bundled_services_are_always_enabled():
    services = _load(BASE_COMPOSE)["services"]
    assert "profiles" not in services["postgres"]
    assert "profiles" not in services["redis"]


# --- external override: honor .env, drop bundled deps ------------------------


def test_external_override_exists():
    assert EXTERNAL_COMPOSE.exists()


def test_external_override_reads_db_settings_from_env():
    env = _env(_load(EXTERNAL_COMPOSE)["services"]["app"])
    assert env["DB_HOST"] != "postgres"
    assert "${DB_HOST" in env["DB_HOST"]
    assert env["DB_PORT"] != "5432"
    assert "${DB_PORT" in env["DB_PORT"]


def test_external_override_routes_queue_through_docker_vars():
    env = _env(_load(EXTERNAL_COMPOSE)["services"]["app"])
    assert "DOCKER_QUEUE_BROKER_URL" in env["QUEUE_BROKER_URL"]
    assert "DOCKER_QUEUE_RESULT_BACKEND" in env["QUEUE_RESULT_BACKEND"]


def test_external_override_drops_bundled_dependencies():
    app = _load(EXTERNAL_COMPOSE)["services"]["app"]
    assert app["depends_on"] is RESET


def test_external_override_parks_bundled_services_behind_profile():
    services = _load(EXTERNAL_COMPOSE)["services"]
    assert "bundled" in services["postgres"]["profiles"]
    assert "bundled" in services["redis"]["profiles"]


# --- docs --------------------------------------------------------------------


def test_env_example_documents_external_deploy():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "DOCKER_QUEUE_BROKER_URL" in text
    assert "docker-compose.external.yml" in text
