import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting
from app.models.source import ProxySource


@pytest.fixture(autouse=True)
def _worker_engine(engine, monkeypatch):
    """Point app.worker's engine at the in-memory test DB."""
    import app.worker

    monkeypatch.setattr(app.worker, "_get_engine", lambda: engine)


class _FakeLock:
    """In-memory stand-in for redis.lock.Lock."""

    def __init__(self, held: set[str], name: str):
        self._held = held
        self.name = name

    def acquire(self, blocking: bool = True) -> bool:
        if self.name in self._held:
            return False
        self._held.add(self.name)
        return True

    def release(self) -> None:
        self._held.discard(self.name)


@pytest.fixture(autouse=True)
def _fake_locks(monkeypatch):
    """Keep the task locks off a real Redis; expose the held-lock names."""
    import app.worker

    held: set[str] = set()

    class _FakeClient:
        def lock(self, name, timeout=None):
            return _FakeLock(held, name)

    monkeypatch.setattr(app.worker, "_get_lock_client", lambda: _FakeClient())
    return held


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


class TestStatsBroadcast:
    def test_broadcasts_stats_after_check(self, engine):
        from app.services.health_service import CheckResult
        from app.worker import check_all_proxies

        _seed(
            engine,
            [
                Proxy(scheme="http", host="1.1.1.1", port=80),
                Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.DEAD),
                Proxy(scheme="http", host="3.3.3.3", port=80),
            ],
        )
        results = [
            CheckResult(alive=True, latency_ms=10.0),
            CheckResult(alive=False, latency_ms=None),
        ]
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(side_effect=results),
        ), patch("app.worker.broadcast_sync") as mock_broadcast:
            check_all_proxies()

        mock_broadcast.assert_called_once_with(
            "stats", {"total": 3, "alive": 1, "dead": 2, "unknown": 0}
        )

    def test_broadcasts_zero_stats_for_empty_pool(self, engine):
        from app.worker import check_all_proxies

        with patch("app.worker.broadcast_sync") as mock_broadcast:
            check_all_proxies()

        mock_broadcast.assert_called_once_with(
            "stats", {"total": 0, "alive": 0, "dead": 0, "unknown": 0}
        )


class TestTaskLocking:
    def test_check_skips_when_lock_held(self, engine, _fake_locks):
        from app.worker import CHECK_LOCK_NAME, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        _fake_locks.add(CHECK_LOCK_NAME)  # another cycle is running

        with patch("app.worker.health_service.check_proxy") as mock_check:
            assert check_all_proxies(force=True) == 0

        mock_check.assert_not_called()

    def test_check_releases_lock_after_run(self, engine, _fake_locks):
        from app.services.health_service import CheckResult
        from app.worker import CHECK_LOCK_NAME, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(return_value=CheckResult(alive=True, latency_ms=1.0)),
        ):
            assert check_all_proxies() == 1

        assert CHECK_LOCK_NAME not in _fake_locks

    def test_check_releases_lock_on_error(self, engine, _fake_locks):
        from app.worker import CHECK_LOCK_NAME, check_all_proxies

        _seed(engine, [Proxy(scheme="http", host="1.1.1.1", port=80)])
        with patch(
            "app.worker.health_service.check_proxy",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with pytest.raises(RuntimeError):
                check_all_proxies()

        assert CHECK_LOCK_NAME not in _fake_locks

    def test_fetch_skips_when_lock_held(self, engine, _fake_locks):
        from app.worker import FETCH_LOCK_NAME, fetch_due_sources

        _fake_locks.add(FETCH_LOCK_NAME)

        with patch("app.worker.fetch_and_import") as mock_fetch:
            assert fetch_due_sources() == 0

        mock_fetch.assert_not_called()

    def test_fetch_releases_lock_after_run(self, engine, _fake_locks):
        from app.worker import FETCH_LOCK_NAME, fetch_due_sources

        with patch("app.worker.fetch_and_import", return_value="ok"):
            fetch_due_sources()

        assert FETCH_LOCK_NAME not in _fake_locks


class TestBeatSchedule:
    def test_schedule_is_fixed_tick(self):
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["check-all-proxies"]
        assert entry["task"] == "app.worker.check_all_proxies"
        # Fixed 60s tick; the task gates on HEALTH_CHECK_INTERVAL from the DB
        assert entry["schedule"] == 60.0

    def test_source_fetch_schedule_configured(self):
        from app.worker import celery_app

        entry = celery_app.conf.beat_schedule["fetch-proxy-sources"]
        assert entry["task"] == "app.worker.fetch_due_sources"
        assert entry["schedule"] == 60.0


class TestFetchDueSources:
    def test_fetches_only_due_sources(self, engine):
        from datetime import datetime, timezone

        from app.worker import fetch_due_sources

        with Session(engine) as session:
            session.add(ProxySource(name="due", url="https://example.com/a.txt"))
            session.add(
                ProxySource(
                    name="not-due",
                    url="https://example.com/b.txt",
                    last_fetched_at=datetime.now(timezone.utc),
                    interval_minutes=60,
                )
            )
            session.add(
                ProxySource(name="disabled", url="https://example.com/c.txt", enabled=False)
            )
            session.commit()

        with patch(
            "app.worker.fetch_and_import", return_value="ok: 0 imported, 0 duplicates"
        ) as mock_fetch, patch("app.worker.seed_default_sources"):
            count = fetch_due_sources()

        assert count == 1
        fetched = {call.args[1].name for call in mock_fetch.call_args_list}
        assert fetched == {"due"}

    def test_seeds_default_sources_on_first_run(self, engine):
        from sqlmodel import select

        from app.worker import fetch_due_sources

        with patch("app.worker.fetch_and_import", return_value="ok"):
            fetch_due_sources()

        with Session(engine) as session:
            names = {s.name for s in session.exec(select(ProxySource)).all()}
        assert "monosans/proxy-list" in names
        assert "TheSpeedX/PROXY-List" in names
