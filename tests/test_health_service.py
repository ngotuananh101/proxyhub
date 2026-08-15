from unittest.mock import MagicMock, patch

import httpx

from app.models.proxy import Proxy
from app.services.health_service import CheckResult, build_proxy_url, check_proxy


def _proxy(**kwargs) -> Proxy:
    defaults = {"scheme": "http", "host": "1.2.3.4", "port": 8080}
    return Proxy(**{**defaults, **kwargs})


class TestBuildProxyUrl:
    def test_without_credentials(self):
        assert build_proxy_url(_proxy()) == "http://1.2.3.4:8080"

    def test_with_credentials(self):
        proxy = _proxy(username="user", password="pass")
        assert build_proxy_url(proxy) == "http://user:pass@1.2.3.4:8080"


class TestCheckProxy:
    def test_alive_with_latency(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = check_proxy(_proxy())
        assert result.alive is True
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    def test_dead_on_timeout(self):
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.TimeoutException("timeout")
            )
            result = check_proxy(_proxy())
        assert result == CheckResult(alive=False, latency_ms=None)

    def test_dead_on_connect_error(self):
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.ConnectError("refused")
            )
            result = check_proxy(_proxy())
        assert result == CheckResult(alive=False, latency_ms=None)

    def test_any_http_response_counts_as_alive(self):
        # Proxy hoạt động = có response HTTP, kể cả 403/500 từ target
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            result = check_proxy(_proxy())
        assert result.alive is True

    def test_client_receives_proxy_url_and_timeout(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = response
            check_proxy(_proxy())
        _, kwargs = mock_client.call_args
        assert kwargs["proxy"] == "http://1.2.3.4:8080"
        assert kwargs["timeout"] == 10.0
