from fastapi.testclient import TestClient


def test_healthz_returns_ok_without_auth(engine):
    from app.main import create_app

    with TestClient(create_app(engine)) as client:
        resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
