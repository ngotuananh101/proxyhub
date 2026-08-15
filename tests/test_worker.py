import asyncio
from unittest.mock import AsyncMock, patch

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
    def test_checks_only_http_and_https(self, engine):
        ids = _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(scheme="https", host="2.2.2.2", port=443),
                Proxy(scheme="socks5", host="3.3.3.3", port=1080),
            ],
        )
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=10.0)),
        ):
            count = check_all_proxies()

        assert count == 2  # socks5 bị bỏ qua
        with Session(engine) as session:
            socks = session.get(Proxy, ids[2])
            assert socks.status == ProxyStatus.UNKNOWN  # không đụng tới
            assert socks.last_checked_at is None

    def test_empty_pool_returns_zero(self, engine):
        from app.worker import check_all_proxies

        assert check_all_proxies() == 0

    def test_marks_alive_and_dead(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        ids = _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(scheme="http", host="2.2.2.2", port=80),
            ],
        )
        results = [
            CheckResult(alive=True, latency_ms=123.45),
            CheckResult(alive=False, latency_ms=None),
        ]
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(side_effect=results),
        ):
            count = check_all_proxies()

        assert count == 2
        with Session(engine) as session:
            alive = session.get(Proxy, ids[0])
            assert alive.status == ProxyStatus.ALIVE
            assert alive.latency_ms == 123.45
            assert alive.last_checked_at is not None

            dead = session.get(Proxy, ids[1])
            assert dead.status == ProxyStatus.DEAD
            assert dead.latency_ms is None
            assert dead.last_checked_at is not None

    def test_concurrency_is_limited(self, engine, monkeypatch):
        from app.core.config import settings
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        monkeypatch.setattr(settings, "HEALTH_CHECK_CONCURRENCY", 2)
        _seed(
            engine,
            [Proxy(scheme="http", host=f"10.0.0.{i}", port=80) for i in range(4)],
        )

        current = 0
        peak = 0

        async def _tracked(proxy):
            nonlocal current, peak
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.01)
            current -= 1
            return CheckResult(alive=True, latency_ms=1.0)

        with patch("app.worker.health_service.check_proxy", new=_tracked):
            count = check_all_proxies()

        assert count == 4
        assert peak <= 2


class TestBeatSchedule:
    def test_schedule_configured(self):
        from app.core.config import settings
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["check-all-proxies"]
        assert entry["task"] == "app.worker.check_all_proxies"
        assert entry["schedule"] == settings.HEALTH_CHECK_INTERVAL
