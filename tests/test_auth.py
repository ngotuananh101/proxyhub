# tests/test_auth.py
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.deps import verify_internal_key
from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="admin_user")
def admin_user_fixture(engine):
    with Session(engine) as session:
        user = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_login_success(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_token(client, admin_user):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_me_invalid_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


def test_me_user_not_found(client):
    from app.core.security import create_access_token
    token = create_access_token({"sub": "99999"})
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "User not found"


def test_verify_internal_key():
    from app.core.config import settings
    # Valid key should not raise
    verify_internal_key(settings.INTERNAL_API_KEY)

    # Invalid key should raise 401
    with pytest.raises(HTTPException) as exc_info:
        verify_internal_key("wrong_key")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid internal key"


def _auth_headers(client) -> dict:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_update_me_success(client, admin_user):
    headers = _auth_headers(client)
    resp = client.put(
        "/api/auth/me",
        json={"username": "newname", "email": "new@example.com"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "newname"
    assert data["email"] == "new@example.com"

    # Login works with the new username
    resp = client.post("/api/auth/login", json={"username": "newname", "password": "admin123"})
    assert resp.status_code == 200


def test_update_me_requires_auth(client):
    resp = client.put("/api/auth/me", json={"username": "x", "email": None})
    assert resp.status_code == 401


def test_update_me_username_conflict(client, engine, admin_user):
    with Session(engine) as session:
        session.add(User(username="other", hashed_password=hash_password("pass1234")))
        session.commit()
    headers = _auth_headers(client)
    resp = client.put("/api/auth/me", json={"username": "other", "email": None}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Username already taken"


def test_update_me_email_conflict(client, engine, admin_user):
    with Session(engine) as session:
        session.add(User(username="other", hashed_password=hash_password("pass1234"), email="taken@example.com"))
        session.commit()
    headers = _auth_headers(client)
    resp = client.put(
        "/api/auth/me",
        json={"username": "admin", "email": "taken@example.com"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email already in use"


def test_update_me_invalid_email(client, admin_user):
    headers = _auth_headers(client)
    resp = client.put("/api/auth/me", json={"username": "admin", "email": "not-an-email"}, headers=headers)
    assert resp.status_code == 422


def test_change_password_success(client, admin_user):
    headers = _auth_headers(client)
    resp = client.put(
        "/api/auth/password",
        json={"current_password": "admin123", "new_password": "newpass456"},
        headers=headers,
    )
    assert resp.status_code == 204

    # Old password no longer works, new one does
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 401
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "newpass456"})
    assert resp.status_code == 200


def test_change_password_wrong_current(client, admin_user):
    headers = _auth_headers(client)
    resp = client.put(
        "/api/auth/password",
        json={"current_password": "wrong", "new_password": "newpass456"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Current password is incorrect"


def test_change_password_too_short(client, admin_user):
    headers = _auth_headers(client)
    resp = client.put(
        "/api/auth/password",
        json={"current_password": "admin123", "new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_change_password_requires_auth(client):
    resp = client.put(
        "/api/auth/password",
        json={"current_password": "admin123", "new_password": "newpass456"},
    )
    assert resp.status_code == 401

