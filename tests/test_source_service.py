from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlmodel import Session, select

from app.models.proxy import Proxy, ProxyStatus
from app.models.source import ProxySource
from app.services.source_service import (
    fetch_and_import,
    import_source_text,
    is_due,
    normalize_line,
    purge_old_dead_proxies,
    seed_default_sources,
)


class TestNormalizeLine:
    def test_bare_ip_port_defaults_to_http(self):
        assert normalize_line("1.2.3.4:8080") == "http://1.2.3.4:8080"

    def test_full_url_kept(self):
        assert normalize_line("socks5://1.2.3.4:1080") == "socks5://1.2.3.4:1080"

    def test_blank_and_comments_dropped(self):
        assert normalize_line("") is None
        assert normalize_line("   ") is None
        assert normalize_line("# comment") is None

    def test_strips_whitespace(self):
        assert normalize_line("  1.2.3.4:80  ") == "http://1.2.3.4:80"


class TestImportSourceText:
    def test_imports_new_proxies_as_unknown(self, session):
        imported, duplicates = import_source_text(
            session, "1.1.1.1:80\n2.2.2.2:8080\nsocks5://3.3.3.3:1080"
        )
        assert (imported, duplicates) == (3, 0)
        proxies = session.exec(select(Proxy)).all()
        assert all(p.status == ProxyStatus.UNKNOWN for p in proxies)

    def test_skips_duplicates_within_text_and_db(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80))
        session.commit()
        imported, duplicates = import_source_text(
            session, "1.1.1.1:80\n1.1.1.1:80\n2.2.2.2:80"
        )
        # First 1.1.1.1:80 hits the DB duplicate; the repeat within the text
        # is dropped silently; 2.2.2.2:80 is new.
        assert (imported, duplicates) == (1, 1)

    def test_skips_garbage_lines(self, session):
        text = "---------- [ ProxyList.to ] ----------\nHTTP Proxies\n1.1.1.1:80\n"
        imported, duplicates = import_source_text(session, text)
        assert (imported, duplicates) == (1, 0)

    def test_does_not_touch_existing_proxy_status(self, session):
        session.add(
            Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE)
        )
        session.commit()
        import_source_text(session, "1.1.1.1:80")
        proxy = session.exec(select(Proxy)).one()
        assert proxy.status == ProxyStatus.ALIVE


class TestPurgeOldDeadProxies:
    def _seed(self, session, status: ProxyStatus, age_days: float, host: str) -> Proxy:
        proxy = Proxy(
            scheme="http",
            host=host,
            port=80,
            status=status,
            updated_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        )
        session.add(proxy)
        session.commit()
        return proxy

    def test_removes_dead_older_than_retention(self, session):
        old_dead = self._seed(session, ProxyStatus.DEAD, 8, "9.9.9.1")
        self._seed(session, ProxyStatus.DEAD, 1, "9.9.9.2")  # recent dead kept
        self._seed(session, ProxyStatus.ALIVE, 30, "9.9.9.3")  # alive never purged
        removed = purge_old_dead_proxies(session, retention_days=7)
        assert removed == 1
        remaining = session.exec(select(Proxy)).all()
        assert old_dead.id not in {p.id for p in remaining}
        assert len(remaining) == 2

    def test_disabled_when_retention_is_zero(self, session):
        self._seed(session, ProxyStatus.DEAD, 30, "9.9.9.1")
        assert purge_old_dead_proxies(session, retention_days=0) == 0
        assert len(session.exec(select(Proxy)).all()) == 1


class TestIsDue:
    def _source(self, **kwargs) -> ProxySource:
        defaults = {"name": "s", "url": "http://x", "enabled": True, "interval_minutes": 60}
        return ProxySource(**{**defaults, **kwargs})

    def test_due_when_never_fetched(self):
        assert is_due(self._source(), datetime.now(timezone.utc)) is True

    def test_not_due_when_disabled(self):
        source = self._source(enabled=False)
        assert is_due(source, datetime.now(timezone.utc)) is False

    def test_not_due_before_interval_elapsed(self):
        source = self._source(last_fetched_at=datetime.now(timezone.utc) - timedelta(minutes=30))
        assert is_due(source, datetime.now(timezone.utc)) is False

    def test_due_after_interval_elapsed(self):
        source = self._source(last_fetched_at=datetime.now(timezone.utc) - timedelta(minutes=61))
        assert is_due(source, datetime.now(timezone.utc)) is True


class TestFetchAndImport:
    def test_success_records_status_and_imports(self, session):
        source = ProxySource(name="s", url="https://example.com/list.txt")
        session.add(source)
        session.commit()

        with patch(
            "app.services.source_service._download",
            new=AsyncMock(return_value="1.1.1.1:80\n2.2.2.2:80"),
        ):
            status = fetch_and_import(session, source, timeout=5, retention_days=0)

        assert status.startswith("ok: 2 imported")
        assert len(session.exec(select(Proxy)).all()) == 2
        session.refresh(source)
        assert source.last_fetched_at is not None
        assert source.last_status == status

    def test_failure_records_error_status(self, session):
        source = ProxySource(name="s", url="https://example.com/list.txt")
        session.add(source)
        session.commit()

        with patch(
            "app.services.source_service._download",
            new=AsyncMock(side_effect=Exception("boom")),
        ):
            status = fetch_and_import(session, source, timeout=5, retention_days=0)

        assert status.startswith("error:")
        session.refresh(source)
        assert source.last_fetched_at is not None


class TestSeedDefaultSources:
    def test_idempotent(self, session):
        seed_default_sources(session)
        seed_default_sources(session)
        assert len(session.exec(select(ProxySource)).all()) == 2
