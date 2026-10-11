# tests/test_dev.py
"""Tests for the pure helpers in dev.py that resolve ports and derived URLs."""

from dev import (
    DEFAULT_APP_PORT,
    DEFAULT_FRONTEND_PORT,
    DEFAULT_GATEWAY_PORT,
    _backend_urls,
    _cors_origins,
    _dev_commands,
    _frontend_urls,
    _ports,
)


def test_ports_defaults_when_env_empty():
    assert _ports({}) == (DEFAULT_APP_PORT, DEFAULT_GATEWAY_PORT, DEFAULT_FRONTEND_PORT)


def test_ports_defaults_are_conventional():
    assert (DEFAULT_APP_PORT, DEFAULT_GATEWAY_PORT, DEFAULT_FRONTEND_PORT) == (
        8000,
        8899,
        5173,
    )


def test_ports_reads_configured_values():
    env = {"APP_PORT": "9000", "GATEWAY_PORT": "9001", "FRONTEND_PORT": "4000"}
    assert _ports(env) == (9000, 9001, 4000)


def test_ports_falls_back_on_invalid_values():
    env = {"APP_PORT": "not-a-port", "GATEWAY_PORT": "", "FRONTEND_PORT": "abc"}
    assert _ports(env) == (DEFAULT_APP_PORT, DEFAULT_GATEWAY_PORT, DEFAULT_FRONTEND_PORT)


def test_backend_urls_follow_app_port():
    urls = _backend_urls(9000)
    assert urls == {
        "GATEWAY_API_URL": "http://127.0.0.1:9000/internal/proxies",
        "GATEWAY_SESSION_URL": "http://127.0.0.1:9000/internal/gateway/session",
        "GATEWAY_LOG_URL": "http://127.0.0.1:9000/internal/logs",
    }


def test_frontend_urls_follow_app_port():
    urls = _frontend_urls(9000)
    assert urls == {
        "VITE_API_URL": "http://localhost:9000",
        "VITE_WS_URL": "ws://localhost:9000",
    }


def test_cors_origins_appends_frontend_port():
    result = _cors_origins("http://localhost:5173", 4000)
    origins = result.split(",")
    assert "http://localhost:5173" in origins
    assert "http://localhost:4000" in origins
    assert "http://127.0.0.1:4000" in origins


def test_cors_origins_does_not_duplicate():
    result = _cors_origins("http://localhost:4000", 4000)
    origins = result.split(",")
    assert origins.count("http://localhost:4000") == 1


def test_cors_origins_handles_empty_existing():
    result = _cors_origins("", 4000)
    origins = result.split(",")
    assert "http://localhost:4000" in origins
    assert "" not in origins


def test_dev_commands_use_configured_ports():
    cmds = dict(_dev_commands(9000, 9001, 4000))

    assert "9000" in cmds["api"]
    assert "9001" in cmds["gateway"]
    assert "4000" in cmds["frontend"]
    assert "--port" in cmds["frontend"]
