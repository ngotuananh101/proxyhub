"""The compiled dashboard is served by the API when FRONTEND_DIST is set."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture(name="dist")
def dist_fixture(tmp_path):
    """A stand-in bundle: one hashed asset plus the SPA shell."""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><div id=root></div>")
    (root / "assets" / "app-abc123.js").write_text("console.log('dashboard')\n" * 100)
    return root


@pytest.fixture(name="client")
def client_fixture(engine, dist, monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(settings, "FRONTEND_DIST", str(dist))
    return TestClient(create_app(engine))


def test_index_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "id=root" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_client_routes_fall_back_to_index(client):
    # React Router owns /logs; a reload there is not a file lookup.
    response = client.get("/logs")
    assert response.status_code == 200
    assert "id=root" in response.text


def test_hashed_assets_are_served_as_files(client):
    response = client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert "dashboard" in response.text
    assert "javascript" in response.headers["content-type"]


def test_missing_asset_is_still_a_404(client):
    # A client holding a stale index.html must not get HTML back for a script
    # URL; that surfaces as a syntax error instead of a clean reload.
    response = client.get("/assets/app-gone999.js")
    assert response.status_code == 404


def test_api_paths_never_fall_back_to_index(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert "id=root" not in response.text


def test_reserved_prefixes_match_whole_segments(client):
    # /docstore has no file behind it and is not an API prefix, so it must get
    # the shell; only the exact /docs segment belongs to the API.
    response = client.get("/docstore")
    assert response.status_code == 200
    assert "id=root" in response.text


def test_api_still_answers_normally(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_is_not_served_without_a_configured_dist(engine, monkeypatch):
    # Unset (or a path that no longer exists) must leave routing untouched;
    # otherwise a deployment without a bundle would answer every URL with 404s
    # from StaticFiles instead of the API's own routes.
    from app.main import create_app

    monkeypatch.setattr(settings, "FRONTEND_DIST", str(Path("/nonexistent-proxyhub-dist")))
    with TestClient(create_app(engine)) as client:
        assert client.get("/").status_code == 404


def test_large_assets_are_compressed(client):
    # Served by the API process instead of Nginx, so compression has to come
    # from the app; a 240 kB JS chunk gzipped to ~2 kB proves it ran.
    response = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
