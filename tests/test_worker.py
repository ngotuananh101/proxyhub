import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting


@pytest.fixture(autouse=True)
def _worker_engine(engine, monkeypatch):
    """Point app.worker's engine at the in-memory test DB."""
    import app.worker

    monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)


def _seed(engine, proxies: list[Proxy]) -> list[int]:
    with Session(engine) as session:
        for p in proxies:
            session.add(p)
        session.commit()
        return [p.id for p in proxies]


def _set_setting(engine, key: str, value: str) -> None:
    with Session(engine) as session:
        row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if row is None:
            row = AppSetting(key=key, value=value)
        else:
            row.value = value
        session.add(row)
        session.commit()


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

        assert count == 2  # socks5 is skipped
        with Session(engine) as session:
            socks = session.get(Proxy, ids[2])
            assert socks.status == ProxyStatus.UNKNOWN  # left untouched
            assert socks.last_checked_at is None

    def test_empty_pool_returns_zero(self, engine):
        from app.worker import check_all_proxies

        assert check_all_proxies() == 0

    def test_skips_dead_proxies(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        ids = _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(
                    scheme="http",
                    host="2.2.2.2",
                    port=80,
                    status=ProxyStatus.DEAD,
                ),
            ],
        )
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=10.0)),
        ) as mock_check:
            count = check_all_proxies()

        assert count == 1  # dead proxy is skipped
        assert mock_check.call_count == 1
        with Session(engine) as session:
            dead = session.get(Proxy, ids[1])
            assert dead.status == ProxyStatus.DEAD  # left untouched
            assert dead.last_checked_at is None

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

    def test_concurrency_is_limited(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        _set_setting(engine, "HEALTH_CHECK_CONCURRENCY", "2")
        _seed(
            engine,
            [Proxy(scheme="http", host=f"10.0.0.{i}", port=80) for i in range(4)],
        )

        current = 0
        peak = 0

        async def _tracked(proxy, url, timeout):
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

    def test_uses_settings_from_db(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        _set_setting(engine, "HEALTH_CHECK_URL", "https://example.com/ip")
        _set_setting(engine, "HEALTH_CHECK_TIMEOUT", "9")
        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])

        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ) as mock_check:
            check_all_proxies()

        args, _ = mock_check.call_args
        assert args[1] == "https://example.com/ip"
        assert args[2] == 9.0


class TestIntervalGating:
    def test_skips_when_interval_not_elapsed(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import LAST_RUN_KEY, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        _set_setting(
            engine,
            LAST_RUN_KEY,
            (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
        )
        _set_setting(engine, "HEALTH_CHECK_INTERVAL", "300")

        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ) as mock_check:
            count = check_all_proxies()

        assert count == 0
        assert mock_check.call_count == 0

    def test_runs_when_interval_elapsed(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import LAST_RUN_KEY, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        _set_setting(
            engine,
            LAST_RUN_KEY,
            (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat(),
        )
        _set_setting(engine, "HEALTH_CHECK_INTERVAL", "300")

        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ):
            assert check_all_proxies() == 1

    def test_force_bypasses_gating(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import LAST_RUN_KEY, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        _set_setting(
            engine,
            LAST_RUN_KEY,
            datetime.now(timezone.utc).isoformat(),  # just ran
        )

        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ):
            assert check_all_proxies(force=True) == 1

    def test_marks_last_run_after_check(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import LAST_RUN_KEY, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ):
            check_all_proxies()

        with Session(engine) as session:
            row = session.exec(select(AppSetting).where(AppSetting.key == LAST_RUN_KEY)).first()
        assert row is not None
        last_run = datetime.fromisoformat(row.value)
        assert (datetime.now(timezone.utc) - last_run).total_seconds() < 60


class TestBeatSchedule:
    def test_schedule_is_fixed_tick(self):
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["check-all-proxies"]
        assert entry["task"] == "app.worker.check_all_proxies"
        # Fixed 60s tick; the task gates on HEALTH_CHECK_INTERVAL from the DB
        assert entry["schedule"] == 60.0
