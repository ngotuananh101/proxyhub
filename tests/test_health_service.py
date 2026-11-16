import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.proxy import Proxy
from app.services.health_service import (
    CheckResult,
    build_proxy_url,
    check_proxy,
    get_ssl_context,
)

URL = "https://api.ipify.org"
TIMEOUT = 6.0


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
    @pytest.mark.anyio
    async def test_alive_with_latency(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=response
            )
            result = await check_proxy(_proxy(), URL, TIMEOUT)
        assert result.alive is True
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.anyio
    async def test_dead_on_timeout(self):
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            result = await check_proxy(_proxy(), URL, TIMEOUT)
        assert result == CheckResult(alive=False, latency_ms=None)

    @pytest.mark.anyio
    async def test_dead_on_connect_error(self):
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("refused")
            )
            result = await check_proxy(_proxy(), URL, TIMEOUT)
        assert result == CheckResult(alive=False, latency_ms=None)

    @pytest.mark.anyio
    async def test_any_http_response_counts_as_alive(self):
        # A working proxy = any HTTP response, even 403/500 from the target
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=response
            )
            result = await check_proxy(_proxy(), URL, TIMEOUT)
        assert result.alive is True

    @pytest.mark.anyio
    async def test_client_receives_proxy_url_and_timeout(self):
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=response
            )
            await check_proxy(_proxy(), URL, 9.5)
        _, kwargs = mock_client.call_args
        assert kwargs["proxy"] == "http://1.2.3.4:8080"
        assert kwargs["timeout"] == 9.5

    @pytest.mark.anyio
    async def test_client_reuses_the_process_wide_ssl_context(self):
        # httpx builds a fresh SSL context (full CA-bundle parse, ~7 ms of
        # blocking work on the event loop) for every client when verify=True.
        # Each check needs its own client for a different upstream proxy, so the
        # context is the shareable part.
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        with patch("app.services.health_service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=response
            )
            await check_proxy(_proxy(), URL, TIMEOUT)
            await check_proxy(_proxy(), URL, TIMEOUT)

        first = mock_client.call_args_list[0][1]["verify"]
        second = mock_client.call_args_list[1][1]["verify"]
        assert isinstance(first, ssl.SSLContext)
        assert first is second


def test_get_ssl_context_is_cached():
    assert get_ssl_context() is get_ssl_context()
