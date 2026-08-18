from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models.log import RequestLog
from app.services.log_service import purge_old_request_logs


def _seed(session, age_days: float, host: str) -> None:
    session.add(
        RequestLog(
            host=host,
            created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        )
    )
    session.commit()


class TestPurgeOldRequestLogs:
    def test_removes_logs_older_than_retention(self, session):
        _seed(session, 31, "old.example.com")
        _seed(session, 10, "recent.example.com")

        removed = purge_old_request_logs(session, retention_days=30)

        assert removed == 1
        hosts = {log.host for log in session.exec(select(RequestLog)).all()}
        assert hosts == {"recent.example.com"}

    def test_disabled_when_retention_is_zero(self, session):
        _seed(session, 60, "old.example.com")
        assert purge_old_request_logs(session, retention_days=0) == 0
        assert len(session.exec(select(RequestLog)).all()) == 1

    def test_keeps_logs_within_retention(self, session):
        _seed(session, 29.9, "just-within.example.com")
        assert purge_old_request_logs(session, retention_days=30) == 0
        assert len(session.exec(select(RequestLog)).all()) == 1
