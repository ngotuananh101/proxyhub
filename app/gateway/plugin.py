"""RotateProxyPlugin — proxy.py plugin that fetches a proxy from ProxyHub backend per request."""
import base64
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import httpx
from proxy.common.constants import COLON
from proxy.common.utils import bytes_, text_
from proxy.core.base import TcpUpstreamConnectionHandler
from proxy.http import Url, httpHeaders
from proxy.http.exception import HttpProtocolException
from proxy.http.parser import HttpParser
from proxy.http.proxy import HttpProxyBasePlugin

logger = logging.getLogger(__name__)

GATEWAY_API_URL = os.environ.get("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
GATEWAY_LOG_URL = os.environ.get(
    "GATEWAY_LOG_URL", GATEWAY_API_URL.rsplit("/", 1)[0] + "/logs"
)
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
API_TIMEOUT = 2.0


def fetch_proxy_from_api(api_url: str, api_key: str) -> tuple[Optional[Url], Optional[str]]:
    """Call the internal API to get one usable proxy and the default target URL. Returns (Url, target_url) or (None, None)."""
    try:
        resp = httpx.get(
            api_url,
            params={"strategy": "random"},
            headers={"X-Internal-Key": api_key},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        logger.error("Failed to reach backend API: %s", e)
        return None, None

    if resp.status_code != 200:
        logger.warning("Backend returned %d: %s", resp.status_code, resp.text)
        return None, None

    data = resp.json()
    # Build proxy URL: scheme://[user:pass@]host:port
    auth = ""
    if data.get("username") and data.get("password"):
        auth = f"{data['username']}:{data['password']}@"
    url_str = f"{data['scheme']}://{auth}{data['host']}:{data['port']}"
    return Url.from_bytes(bytes_(url_str)), data.get("default_target_url")


def send_access_log(payload: Dict[str, Any]) -> None:
    """POST one access-log entry to the backend. Fire-and-forget."""
    try:
        httpx.post(
            GATEWAY_LOG_URL,
            json=payload,
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Failed to send access log: %s", e)


class RotateProxyPlugin(TcpUpstreamConnectionHandler, HttpProxyBasePlugin):
    """Fetches a random alive proxy from ProxyHub backend for each request."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._endpoint: Optional[Url] = None
        self._default_target: Optional[str] = None
        self._metadata: List[Any] = [None, None, None, None]

    def handle_upstream_data(self, raw: memoryview) -> None:
        self.client.queue(raw)

    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        """Fetch proxy from API and connect to it. Return None to skip default upstream."""
        self._endpoint, self._default_target = fetch_proxy_from_api(
            GATEWAY_API_URL, INTERNAL_API_KEY
        )
        if self._endpoint is None:
            raise HttpProtocolException("No available proxy from ProxyHub backend")

        assert self._endpoint.hostname and self._endpoint.port
        endpoint_tuple = (text_(self._endpoint.hostname), self._endpoint.port)
        logger.info("Using upstream proxy %s:%s", *endpoint_tuple)

        self.initialize_upstream(*endpoint_tuple)
        assert self.upstream
        try:
            self.upstream.connect()
        except TimeoutError:
            raise HttpProtocolException(
                f"Timed out connecting to upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        except ConnectionRefusedError:
            raise HttpProtocolException(
                f"Connection refused by upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        return None

    def handle_client_request(self, request: HttpParser) -> Optional[HttpParser]:
        """Forward request to upstream proxy, adding Proxy-Authorization if needed."""
        if not self.upstream:
            return request

        # If the client sent a direct request without a remote target host (e.g. browsing directly to gateway :8899),
        # rewrite to default target from health check settings.
        if (
            self._default_target
            and not request.is_https_tunnel
            and (
                not request.has_header(b"host")
                or not request.path
                or not request.path.startswith(b"http://")
            )
        ):
            target_url = Url.from_bytes(bytes_(self._default_target))
            if target_url.hostname:
                target_port = target_url.port or (443 if target_url.scheme == b"https" else 80)
                request.add_header(
                    b"Host",
                    target_url.hostname
                    + (b":" + bytes_(str(target_port)) if target_url.port else b""),
                )
                request.path = bytes_(self._default_target)

        # Track metadata for access log
        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        method = None if not request.method else request.method.decode()
        self._metadata = [host, port, path, method]

        # Add Proxy-Authorization header if credentials exist
        if self._endpoint and self._endpoint.has_credentials:
            assert self._endpoint.username and self._endpoint.password
            request.add_header(
                httpHeaders.PROXY_AUTHORIZATION,
                b"Basic " + base64.b64encode(
                    self._endpoint.username + COLON + self._endpoint.password
                ),
            )

        self.upstream.queue(memoryview(request.build(for_proxy=True)))
        return request

    def handle_client_data(self, raw: memoryview) -> Optional[memoryview]:
        """Queue client data to upstream proxy."""
        assert self.upstream
        self.upstream.queue(raw)
        return raw

    def handle_upstream_chunk(self, chunk: memoryview) -> Optional[memoryview]:
        """Should never be called since we manage upstream manually."""
        if not self.upstream:
            return chunk
        raise Exception("handle_upstream_chunk should not be called")

    def on_upstream_connection_close(self) -> None:
        if self.upstream and not self.upstream.closed:
            self.upstream.close()
            self.upstream = None

    def on_access_log(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.upstream:
            return context
        addr, port = (self.upstream.addr[0], self.upstream.addr[1])
        context.update({
            "upstream_proxy_host": addr,
            "upstream_proxy_port": port,
            "server_host": self._metadata[0],
            "server_port": self._metadata[1],
            "request_path": self._metadata[2],
            "response_bytes": self.total_size,
        })
        logger.info(
            "%s:%s %s %s:%s%s -> %s:%s",
            context.get("client_ip"), context.get("client_port"),
            self._metadata[3], self._metadata[0], self._metadata[1],
            self._metadata[2] or "", addr, port,
        )
        # Push to the backend for the realtime log feed (never blocks proxying)
        threading.Thread(
            target=send_access_log,
            args=({
                "client_ip": context.get("client_ip"),
                "method": self._metadata[3],
                "host": self._metadata[0],
                "path": self._metadata[2],
                "proxy_host": addr,
                "proxy_port": port,
                "response_bytes": self.total_size,
            },),
            daemon=True,
        ).start()
        return None
