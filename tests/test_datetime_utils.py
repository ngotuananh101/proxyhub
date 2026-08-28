from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.datetime_utils import is_valid_timezone, utc_isoformat
from app.core.security import hash_password
from app.models.log import RequestLog
from app.models.tenant import Tenant
from app.models.user import User


class TestUtcIsoformat:
    def test_naive_datetime_gets_utc_offset(self):
        # SQLite hands datetimes back with tzinfo=None; the serialized string
        # must still carry the offset so browsers parse it as UTC.
        value = datetime(2026, 8, 16, 12, 30, 45)
        assert utc_isoformat(value) == "2026-08-16T12:30:45+00:00"

    def test_aware_datetime_converted_to_utc(self):
        plus7 = timezone(timedelta(hours=7))
        value = datetime(2026, 8, 16, 19, 30, 45, tzinfo=plus7)
        assert utc_isoformat(value) == "2026-08-16T12:30:45+00:00"

    def test_utc_datetime_kept_as_is(self):
        value = datetime(2026, 8, 16, 12, 30, 45, tzinfo=timezone.utc)
        assert utc_isoformat(value) == "2026-08-16T12:30:45+00:00"


class TestIsValidTimezone:
    def test_accepts_utc_and_iana_zones(self):
        assert is_valid_timezone("UTC")
        assert is_valid_timezone("Asia/Ho_Chi_Minh")
        assert is_valid_timezone("America/New_York")

    def test_rejects_unknown_names(self):
        assert not is_valid_timezone("Not/AZone")
        assert not is_valid_timezone("ICT")
        assert not is_valid_timezone("")


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        session.add(
            User(username="tzuser", hashed_password=hash_password("tzpass123"), is_admin=True)
        )
        session.commit()
    resp = client.post(
        "/api/auth/login", json={"username": "tzuser", "password": "tzpass123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestApiEmitsUtcOffsets:
    def test_logs_created_at_has_utc_offset(self, client, auth_headers, engine):
        with Session(engine) as session:
            tenant = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
            session.add(RequestLog(method="GET", host="example.com", path="/", tenant_id=tenant.id))
            session.commit()

        resp = client.get("/api/logs", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["items"][0]["created_at"].endswith("+00:00")

    def test_sources_created_at_has_utc_offset(self, client, auth_headers):
        created = client.post(
            "/api/sources",
            json={"name": "tz-src", "url": "https://example.com/p.txt"},
            headers=auth_headers,
        ).json()

        resp = client.get("/api/sources", headers=auth_headers)
        assert resp.status_code == 200
        source = next(s for s in resp.json() if s["id"] == created["id"])
        assert source["created_at"].endswith("+00:00")

    def test_proxies_created_at_has_utc_offset(self, client, auth_headers):
        created = client.post(
            "/api/proxies",
            json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
            headers=auth_headers,
        )
        assert created.status_code == 201
        assert created.json()["created_at"].endswith("+00:00")
        assert created.json()["updated_at"].endswith("+00:00")
