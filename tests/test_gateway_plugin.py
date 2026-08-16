# tests/test_gateway_plugin.py
import json
from unittest.mock import MagicMock, patch

from app.gateway.plugin import RotateProxyPlugin, fetch_proxy_from_api


class TestFetchProxyFromApi:
    @patch("app.gateway.plugin.httpx.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 1, "scheme": "http", "host": "1.2.3.4",
            "port": 8080, "username": "user", "password": "pass",
            "default_target_url": "https://api.ipify.org",
        }
        mock_get.return_value = mock_resp

        result, default_target = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is not None
        assert result.hostname == b"1.2.3.4"
        assert result.port == 8080
        assert default_target == "https://api.ipify.org"

    @patch("app.gateway.plugin.httpx.get")
    def test_no_proxy_available(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result, default_target = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None
        assert default_target is None

    @patch("app.gateway.plugin.httpx.get")
    def test_backend_down(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        result, default_target = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None
        assert default_target is None


class TestAccessLogPayload:
    def _make_plugin(self):
        # Bypass the real __init__ (needs proxy.py's connection-handler args)
        plugin = RotateProxyPlugin.__new__(RotateProxyPlugin)
        plugin.upstream = MagicMock()
        plugin.upstream.addr = ("34.43.46.91", 80)
        plugin.total_size = 512
        plugin._endpoint = None
        return plugin

    def test_payload_is_json_serializable(self):
        """proxy.py hands us bytes for method/path; the pushed payload must be str."""
        plugin = self._make_plugin()
        request = MagicMock()
        request.has_header.return_value = True
        request.header.return_value = b"httpbin.org:80"
        request.path = b"/ip"
        request.method = b"GET"
        request.is_https_tunnel = False
        request.build.return_value = b"GET /ip HTTP/1.1\r\n\r\n"

        plugin.handle_client_request(request)

        with patch("app.gateway.plugin.threading.Thread") as mock_thread:
            plugin.on_access_log({"client_ip": "127.0.0.1", "client_port": 10902})

        payload = mock_thread.call_args.kwargs["args"][0]
        assert payload["method"] == "GET"
        assert payload["host"] == "httpbin.org"
        assert payload["path"] == "/ip"
        assert payload["proxy_host"] == "34.43.46.91"
        assert payload["proxy_port"] == 80
        json.dumps(payload)  # would raise TypeError if any bytes leaked in
