# tests/test_gateway_plugin.py
import json
from unittest.mock import patch, MagicMock
import pytest

from app.gateway.plugin import RotateProxyPlugin, fetch_proxy_from_api


class TestFetchProxyFromApi:
    @patch("app.gateway.plugin.httpx.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 1, "scheme": "http", "host": "1.2.3.4",
            "port": 8080, "username": "user", "password": "pass",
        }
        mock_get.return_value = mock_resp

        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is not None
        assert result.hostname == b"1.2.3.4"
        assert result.port == 8080

    @patch("app.gateway.plugin.httpx.get")
    def test_no_proxy_available(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None

    @patch("app.gateway.plugin.httpx.get")
    def test_backend_down(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None
