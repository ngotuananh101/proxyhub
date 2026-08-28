"""Comprehensive tenant scoping tests for Task 6."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import hash_password
from app.models.log import RequestLog
from app.models.proxy import Proxy, ProxyStatus
from app.models.source import ProxySource
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app

    app = create_app(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(name="default_tenant_id")
def default_tenant_id_fixture(engine):
    with Session(engine) as session:
        tenant = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
        return tenant.id


@pytest.fixture(name="admin_token")
def admin_token_fixture(engine, client):
    with Session(engine) as session:
        user = User(
            username="admin", hashed_password=hash_password("admin123"), is_admin=True
        )
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(name="second_tenant")
def second_tenant_fixture(engine):
    with Session(engine) as session:
        t = Tenant(name="Second", slug="second")
        session.add(t)
        session.commit()
        return t.id


def _create_member(engine, client, username, tenant_id, role="member"):
    """Create a non-admin user with membership in the given tenant and return auth headers."""
    with Session(engine) as session:
        user = User(
            username=username, hashed_password=hash_password("pass1234"), is_admin=False
        )
        session.add(user)
        session.commit()
        session.add(
            TenantMembership(user_id=user.id, tenant_id=tenant_id, role=role)
        )
        session.commit()
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass1234"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_proxy(client, headers, host, port, scheme="http"):
    return client.post(
        "/api/proxies",
        json={"scheme": scheme, "host": host, "port": port},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Proxy isolation
# ---------------------------------------------------------------------------

class TestProxyIsolation:
    def test_proxies_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """Admin (default tenant) creates a proxy; member of second tenant cannot see it."""
        # Admin creates a proxy in the default tenant
        resp = _create_proxy(client, admin_token, "10.0.0.1", 8080)
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == 1

        # Member of second tenant creates a proxy
        member_headers = _create_member(engine, client, "member_proxy", second_tenant)
        client.post(
            "/api/proxies",
            json={"scheme": "http", "host": "20.0.0.1", "port": 9090},
            headers=member_headers,
        )

        # Admin sees only their proxy
        resp = client.get("/api/proxies", headers=admin_token)
        hosts = {p["host"] for p in resp.json()["items"]}
        assert hosts == {"10.0.0.1"}

        # Member sees only their proxy
        resp = client.get("/api/proxies", headers=member_headers)
        hosts = {p["host"] for p in resp.json()["items"]}
        assert hosts == {"20.0.0.1"}

    def test_create_duplicate_in_same_tenant_returns_409(self, client, admin_token):
        """Duplicate proxy within the same tenant returns 409."""
        body = {"scheme": "http", "host": "1.1.1.1", "port": 80}
        client.post("/api/proxies", json=body, headers=admin_token)
        resp = client.post("/api/proxies", json=body, headers=admin_token)
        assert resp.status_code == 409

    def test_create_duplicate_in_different_tenant_allowed(self, client, admin_token, second_tenant, engine):
        """Same host:port in a different tenant is allowed."""
        body = {"scheme": "http", "host": "1.1.1.1", "port": 80}
        client.post("/api/proxies", json=body, headers=admin_token)

        member_headers = _create_member(engine, client, "member_dup", second_tenant)
        resp = client.post("/api/proxies", json=body, headers=member_headers)
        assert resp.status_code == 201

    def test_cross_tenant_get_returns_404(self, client, admin_token, second_tenant, engine):
        """A member of tenant 2 cannot GET a proxy belonging to tenant 1."""
        resp = _create_proxy(client, admin_token, "10.0.0.1", 8080)
        proxy_id = resp.json()["id"]

        member_headers = _create_member(engine, client, "member_xget", second_tenant)
        resp = client.get(f"/api/proxies/{proxy_id}", headers=member_headers)
        assert resp.status_code == 404

    def test_cross_tenant_update_returns_404(self, client, admin_token, second_tenant, engine):
        """A member of tenant 2 cannot UPDATE a proxy belonging to tenant 1."""
        resp = _create_proxy(client, admin_token, "10.0.0.1", 8080)
        proxy_id = resp.json()["id"]

        member_headers = _create_member(engine, client, "member_xup", second_tenant)
        resp = client.put(f"/api/proxies/{proxy_id}", json={"host": "99.99.99.99"}, headers=member_headers)
        assert resp.status_code == 404

    def test_cross_tenant_delete_returns_404(self, client, admin_token, second_tenant, engine):
        """A member of tenant 2 cannot DELETE a proxy belonging to tenant 1."""
        resp = _create_proxy(client, admin_token, "10.0.0.1", 8080)
        proxy_id = resp.json()["id"]

        member_headers = _create_member(engine, client, "member_xdel", second_tenant)
        resp = client.delete(f"/api/proxies/{proxy_id}", headers=member_headers)
        assert resp.status_code == 404

    def test_delete_many_is_tenant_scoped(self, client, admin_token, second_tenant, engine):
        """A member can only delete their own tenant's proxies, not others'."""
        resp = _create_proxy(client, admin_token, "10.0.0.1", 8080)
        proxy1_id = resp.json()["id"]

        member_headers = _create_member(engine, client, "member_delmany", second_tenant)

        resp2 = client.post(
            "/api/proxies",
            json={"scheme": "http", "host": "20.0.0.1", "port": 9090},
            headers=member_headers,
        )
        proxy2_id = resp2.json()["id"]

        # Member tries to delete both proxies (one from each tenant)
        client.request(
            "DELETE",
            "/api/proxies",
            content=json.dumps({"ids": [proxy1_id, proxy2_id]}),
            headers={**member_headers, "Content-Type": "application/json"},
        )

        # Proxy1 (default tenant) should still exist
        resp = client.get(f"/api/proxies/{proxy1_id}", headers=admin_token)
        assert resp.status_code == 200
        # Proxy2 (second tenant) should be deleted
        resp = client.get(f"/api/proxies/{proxy2_id}", headers=member_headers)
        assert resp.status_code == 404

    def test_import_proxies_scoped_per_tenant(self, client, admin_token):
        """Import assigns the active tenant to created proxies."""
        resp = client.post(
            "/api/proxies/import",
            json={"text": "http://1.1.1.1:80\nhttp://2.2.2.2:80"},
            headers=admin_token,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2

        resp = client.get("/api/proxies", headers=admin_token)
        for p in resp.json()["items"]:
            assert p["tenant_id"] == 1

    def test_clear_dead_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """Clear-dead only deletes dead proxies in the active tenant."""
        with Session(engine) as session:
            t1 = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
            t2 = session.get(Tenant, second_tenant)
            session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.DEAD, tenant_id=t1.id))
            session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.DEAD, tenant_id=t2.id))
            session.commit()

        resp = client.post("/api/proxies/clear-dead", headers=admin_token)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

        # The second tenant's proxy should still exist
        with Session(engine) as session:
            remaining = session.exec(
                select(Proxy).where(Proxy.tenant_id == second_tenant, Proxy.host == "2.2.2.2")
            ).first()
            assert remaining is not None

    def test_list_proxies_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """List returns only proxies in the active tenant."""
        _create_proxy(client, admin_token, "10.0.0.1", 8080)

        member_headers = _create_member(engine, client, "member_list", second_tenant)
        client.post(
            "/api/proxies",
            json={"scheme": "http", "host": "20.0.0.1", "port": 9090},
            headers=member_headers,
        )

        resp = client.get("/api/proxies", headers=admin_token)
        hosts = {p["host"] for p in resp.json()["items"]}
        assert hosts == {"10.0.0.1"}

        resp = client.get("/api/proxies", headers=member_headers)
        hosts = {p["host"] for p in resp.json()["items"]}
        assert hosts == {"20.0.0.1"}


# ---------------------------------------------------------------------------
# Stats scoping
# ---------------------------------------------------------------------------

class TestStatsScoping:
    def test_stats_summary_per_tenant(self, client, admin_token, second_tenant, engine):
        """Stats summary returns counts only for the active tenant."""
        with Session(engine) as session:
            t1 = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
            t2 = session.get(Tenant, second_tenant)
            session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE, tenant_id=t1.id))
            session.add(Proxy(scheme="http", host="1.1.1.2", port=80, status=ProxyStatus.ALIVE, tenant_id=t1.id))
            session.add(Proxy(scheme="http", host="1.1.1.3", port=80, status=ProxyStatus.DEAD, tenant_id=t1.id))
            session.add(Proxy(scheme="http", host="2.1.1.1", port=80, status=ProxyStatus.ALIVE, tenant_id=t2.id))
            session.add(Proxy(scheme="http", host="2.1.1.2", port=80, status=ProxyStatus.UNKNOWN, tenant_id=t2.id))
            session.add(Proxy(scheme="http", host="2.1.1.3", port=80, status=ProxyStatus.UNKNOWN, tenant_id=t2.id))
            session.commit()

        resp = client.get("/api/stats/summary", headers=admin_token)
        data = resp.json()
        assert data["total"] == 3
        assert data["alive"] == 2
        assert data["dead"] == 1
        assert data["unknown"] == 0

        member_headers = _create_member(engine, client, "member_stats", second_tenant)
        resp = client.get("/api/stats/summary", headers=member_headers)
        data = resp.json()
        assert data["total"] == 3
        assert data["alive"] == 1
        assert data["dead"] == 0
        assert data["unknown"] == 2


# ---------------------------------------------------------------------------
# Logs scoping
# ---------------------------------------------------------------------------

class TestLogsScoping:
    def test_logs_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """Logs list returns only logs for the active tenant."""
        with Session(engine) as session:
            t1 = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
            t2 = session.get(Tenant, second_tenant)
            session.add(RequestLog(host="default-a.com", tenant_id=t1.id, created_at=datetime.now(timezone.utc)))
            session.add(RequestLog(host="default-b.com", tenant_id=t1.id, created_at=datetime.now(timezone.utc)))
            session.add(RequestLog(host="second-a.com", tenant_id=t2.id, created_at=datetime.now(timezone.utc)))
            session.commit()

        resp = client.get("/api/logs", headers=admin_token)
        hosts = {log["host"] for log in resp.json()["items"]}
        assert hosts == {"default-a.com", "default-b.com"}

        member_headers = _create_member(engine, client, "member_logs", second_tenant)
        resp = client.get("/api/logs", headers=member_headers)
        hosts = {log["host"] for log in resp.json()["items"]}
        assert hosts == {"second-a.com"}


# ---------------------------------------------------------------------------
# Sources scoping
# ---------------------------------------------------------------------------

class TestSourcesScoping:
    def test_list_sources_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """Sources list returns only sources for the active tenant."""
        with Session(engine) as session:
            t2 = session.get(Tenant, second_tenant)
            session.add(ProxySource(name="second-src", url="https://second.com/list.txt", tenant_id=t2.id))
            session.commit()

        resp = client.get("/api/sources", headers=admin_token)
        names = {s["name"] for s in resp.json()}
        assert "second-src" not in names
        assert "monosans/proxy-list - http" in names

        member_headers = _create_member(engine, client, "member_srcs", second_tenant)
        resp = client.get("/api/sources", headers=member_headers)
        names = {s["name"] for s in resp.json()}
        assert names == {"second-src"}

    def test_create_source_scoped_per_tenant(self, client, admin_token, second_tenant, engine):
        """Source created by a member belongs to that member's tenant."""
        member_headers = _create_member(engine, client, "member_create_src", second_tenant)

        resp = client.post(
            "/api/sources",
            json={"name": "member-src", "url": "https://example.com/p.txt"},
            headers=member_headers,
        )
        assert resp.status_code == 201

        resp = client.get("/api/sources", headers=admin_token)
        names = {s["name"] for s in resp.json()}
        assert "member-src" not in names

        resp = client.get("/api/sources", headers=member_headers)
        names = {s["name"] for s in resp.json()}
        assert "member-src" in names

    def test_cross_tenant_source_update_delete_returns_404(self, client, admin_token, second_tenant, engine):
        """A member cannot update/delete a source belonging to another tenant."""
        resp = client.post(
            "/api/sources",
            json={"name": "default-src", "url": "https://example.com/p.txt"},
            headers=admin_token,
        )
        source_id = resp.json()["id"]

        member_headers = _create_member(engine, client, "member_src_x", second_tenant)

        resp = client.put(
            f"/api/sources/{source_id}",
            json={"name": "hijacked"},
            headers=member_headers,
        )
        assert resp.status_code == 404

        resp = client.delete(f"/api/sources/{source_id}", headers=member_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Header override / validation
# ---------------------------------------------------------------------------

class TestTenantHeaderOverride:
    def test_super_admin_header_override(self, client, admin_token, second_tenant, engine):
        """Super admin can override the tenant via X-Tenant-Id header."""
        with Session(engine) as session:
            t2 = session.get(Tenant, second_tenant)
            session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.ALIVE, tenant_id=t2.id))
            session.commit()

        # Without override, admin sees only default tenant proxies
        resp = client.get("/api/proxies", headers=admin_token)
        hosts = {p["host"] for p in resp.json()["items"]}
        assert "2.2.2.2" not in hosts

        # With header override, admin sees second tenant proxies
        resp = client.get("/api/proxies", headers={**admin_token, "X-Tenant-Id": str(second_tenant)})
        hosts = {p["host"] for p in resp.json()["items"]}
        assert "2.2.2.2" in hosts
        assert resp.json()["items"][0]["tenant_id"] == second_tenant

    def test_non_admin_not_member_of_other_tenant_403(self, client, admin_token, second_tenant, engine):
        """Non-admin user who is not a member of the requested tenant gets 403."""
        member_headers = _create_member(engine, client, "member_no_access", default_tenant_id(engine))

        resp = client.get("/api/proxies", headers={**member_headers, "X-Tenant-Id": str(second_tenant)})
        assert resp.status_code == 403

    def test_invalid_tenant_id_header_400(self, client, admin_token):
        """Invalid X-Tenant-Id header (non-integer) returns 400."""
        resp = client.get("/api/proxies", headers={**admin_token, "X-Tenant-Id": "not-a-number"})
        assert resp.status_code == 400

    def test_non_admin_without_membership_403(self, client, engine):
        """Non-admin user without any membership gets 403."""
        with Session(engine) as session:
            user = User(
                username="no_membership", hashed_password=hash_password("pass1234"), is_admin=False
            )
            session.add(user)
            session.commit()
        resp_login = client.post("/api/auth/login", json={"username": "no_membership", "password": "pass1234"})
        headers = {"Authorization": f"Bearer {resp_login.json()['access_token']}"}

        resp = client.get("/api/proxies", headers=headers)
        assert resp.status_code == 403


def default_tenant_id(engine):
    with Session(engine) as session:
        tenant = session.exec(select(Tenant).where(Tenant.slug == "default")).first()
        return tenant.id
