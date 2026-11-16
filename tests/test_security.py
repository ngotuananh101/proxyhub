import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_long_passphrase_round_trips():
    password = "a-very-long-passphrase-" * 8  # 184 bytes, well past bcrypt's 72
    hashed = hash_password(password)
    assert verify_password(password, hashed)


def test_long_passwords_differing_past_byte_72_do_not_collide():
    shared_prefix = "x" * 72
    hashed = hash_password(shared_prefix + "one")
    assert not verify_password(shared_prefix + "two", hashed)


def test_verify_returns_false_instead_of_raising_on_garbage_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_create_and_decode_token():
    token = create_access_token({"sub": "42"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_expired_token():
    token = create_access_token({"sub": "42"}, expires_delta=-1)
    with pytest.raises(Exception):
        decode_access_token(token)
