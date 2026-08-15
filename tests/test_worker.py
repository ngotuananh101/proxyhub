from unittest.mock import patch

import pytest
from sqlmodel import Session

from app.models.proxy import Proxy, ProxyStatus


@pytest.fixture(autouse=True)
def _worker_engine(engine, monkeypatch):
    """Trỏ engine của app.worker về DB test in-memory."""
    import app.worker

    monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)


def _seed(engine, proxies: list[Proxy]) -> list[int]:
    with Session(engine) as session:
        for p in proxies:
            session.add(p)
        session.commit()
        return [p.id for p in proxies]


class TestCheckAllProxies:
    def test_dispatches_one_task_per_http_proxy(self, engine):
        _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(scheme="https", host="2.2.2.2", port=443),
                Proxy(scheme="socks5", host="3.3.3.3", port=1080),
            ],
        )
        from app.worker import check_all_proxies, check_proxy_task

        with patch.object(check_proxy_task, "delay") as mock_delay:
            count = check_all_proxies()
        assert count == 2  # socks5 bị bỏ qua
        assert mock_delay.call_count == 2

    def test_empty_pool_dispatches_nothing(self, engine):
        from app.worker import check_all_proxies, check_proxy_task

        with patch.object(check_proxy_task, "delay") as mock_delay:
            count = check_all_proxies()
        assert count == 0
        mock_delay.assert_not_called()


class TestCheckProxyTask:
    def test_marks_alive(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_proxy_task

        [proxy_id] = _seed(
            engine, [Proxy(scheme="http", host="1.1.1.1", port=80)]
        )
        with patch(
            "app.worker.health_service.check_proxy",
            return_value=CheckResult(alive=True, latency_ms=123.45),
        ):
            result = check_proxy_task(proxy_id)

        assert result == "alive"
        with Session(engine) as session:
            proxy = session.get(Proxy, proxy_id)
            assert proxy.status == ProxyStatus.ALIVE
            assert proxy.latency_ms == 123.45
            assert proxy.last_checked_at is not None

    def test_marks_dead(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_proxy_task

        [proxy_id] = _seed(
            engine,
            [Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE)],
        )
        with patch(
            "app.worker.health_service.check_proxy",
            return_value=CheckResult(alive=False, latency_ms=None),
        ):
            result = check_proxy_task(proxy_id)

        assert result == "dead"
        with Session(engine) as session:
            proxy = session.get(Proxy, proxy_id)
            assert proxy.status == ProxyStatus.DEAD
            assert proxy.latency_ms is None
            assert proxy.last_checked_at is not None

    def test_missing_proxy_returns_not_found(self, engine):
        from app.worker import check_proxy_task

        assert check_proxy_task(99999) == "not_found"


class TestBeatSchedule:
    def test_schedule_configured(self):
        from app.core.config import settings
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["check-all-proxies"]
        assert entry["task"] == "app.worker.check_all_proxies"
        assert entry["schedule"] == settings.HEALTH_CHECK_INTERVAL
