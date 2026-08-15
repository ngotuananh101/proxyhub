from app.models.proxy import Proxy, ProxyStatus
from app.models.user import User


def test_create_user(session):
    user = User(username="admin", hashed_password="hash123", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    assert user.username == "admin"
    assert user.is_admin is True


def test_create_proxy(session):
    proxy = Proxy(
        scheme="http",
        host="1.2.3.4",
        port=8080,
        username="user1",
        password="pass1",
    )
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    assert proxy.id is not None
    assert proxy.status == ProxyStatus.UNKNOWN
    assert proxy.latency_ms is None


def test_proxy_unique_constraint(session):
    p1 = Proxy(scheme="http", host="1.2.3.4", port=8080)
    session.add(p1)
    session.commit()

    p2 = Proxy(scheme="http", host="1.2.3.4", port=8080)
    session.add(p2)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()
