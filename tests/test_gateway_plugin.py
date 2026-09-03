# tests/test_gateway_plugin.py
import json
from unittest.mock import MagicMock, patch

from app.gateway.plugin import (
    RotateProxyPlugin,
    build_407_response_bytes,
    create_session_from_api,
    extract_basic_auth,
)


def test_extract_basic_auth():
    # Basic dXNlcjpwYXNz => user:pass
    header_val = b"Basic dXNlcjpwYXNz"
    u, p = extract_basic_auth(header_val)
    assert u == "user"
    assert p == "pass"


def test_extract_basic_auth_invalid():
    assert extract_basic_auth(b"Bearer xyz") == (None, None)
    assert extract_basic_auth(b"") == (None, None)
    assert extract_basic_auth(None) == (None, None)


def test_build_407_response_bytes():
    raw = build_407_response_bytes()
    assert b"407 Proxy Authentication Required" in raw
    assert b'Proxy-Authenticate: Basic realm="ProxyHub"' in raw


def test_get_http_client_singleton():
    from app.gateway.plugin import get_http_client
    c1 = get_http_client()
    c2 = get_http_client()
    assert c1 is c2
    assert not c1.is_closed


def test_create_session_from_api_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "tenant_id": 1,
        "credential_id": 10,
        "auth_mode": "basic",
        "proxy": {
            "id": 1,
            "scheme": "http",
            "host": "5.6.7.8",
            "port": 8080,
            "username": "u",
            "password": "p",
        },
        "default_target_url": "https://api.ipify.org",
    }

    with patch("app.gateway.plugin.get_http_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        endpoint, default_target, session_meta = create_session_from_api(
            session_url="http://test/internal/gateway/session",
            api_key="secret",
            client_ip="1.2.3.4",
            username="u",
            password="p",
        )
        assert endpoint is not None
        assert endpoint.hostname == b"5.6.7.8"
        assert endpoint.port == 8080
        assert session_meta["tenant_id"] == 1
        assert session_meta["credential_id"] == 10
        assert session_meta["auth_status"] == "allowed"


def test_create_session_from_api_401():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid credentials"

    with patch("app.gateway.plugin.get_http_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        endpoint, default_target, session_meta = create_session_from_api(
            session_url="http://test/internal/gateway/session",
            api_key="secret",
            client_ip="1.2.3.4",
        )
        assert endpoint is None
        assert session_meta["auth_status"] == "denied"
        assert session_meta["status_code"] == 401


class TestAccessLogPayload:
    def _make_plugin(self):
        plugin = RotateProxyPlugin.__new__(RotateProxyPlugin)
        plugin.upstream = MagicMock()
        plugin.upstream.addr = ("34.43.46.91", 80)
        plugin.total_size = 512
        plugin._endpoint = None
        plugin._default_target = None
        plugin._metadata = [None, None, None, None]
        plugin._session_meta = {
            "tenant_id": 1,
            "credential_id": 10,
            "auth_status": "allowed",
        }
        return plugin

    def test_payload_is_json_serializable(self):
        plugin = self._make_plugin()
        request = MagicMock()
        request.has_header.return_value = True
        request.header.return_value = b"httpbin.org:80"
        request.path = b"/ip"
        request.method = b"GET"
        request.is_https_tunnel = False
        request.build.return_value = b"GET /ip HTTP/1.1\r\n\r\n"

        plugin.handle_client_request(request)

        with patch("app.gateway.plugin._LOG_EXECUTOR.submit") as mock_submit:
            plugin.on_access_log({"client_ip": "127.0.0.1", "client_port": 10902})

        assert mock_submit.called
        payload = mock_submit.call_args[0][1]
        assert payload["method"] == "GET"
        assert payload["host"] == "httpbin.org"
        assert payload["path"] == "/ip"
        assert payload["proxy_host"] == "34.43.46.91"
        assert payload["proxy_port"] == 80
        assert payload["tenant_id"] == 1
        assert payload["auth_credential_id"] == 10
        assert payload["auth_status"] == "allowed"
        json.dumps(payload)
