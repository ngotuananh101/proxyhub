"""RotateProxyPlugin — proxy.py plugin that authenticates clients and fetches a proxy from ProxyHub backend per request."""
import base64
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

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
GATEWAY_SESSION_URL = os.environ.get(
    "GATEWAY_SESSION_URL", GATEWAY_API_URL.rsplit("/", 1)[0] + "/gateway/session"
)
GATEWAY_LOG_URL = os.environ.get(
    "GATEWAY_LOG_URL", GATEWAY_API_URL.rsplit("/", 1)[0] + "/logs"
)
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
API_TIMEOUT = 1.0

_HTTP_CLIENT: Optional[httpx.Client] = None
_CLIENT_LOCK = threading.Lock()
_LOG_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="access_log")


def get_http_client() -> httpx.Client:
    """Return persistent httpx.Client with connection pooling."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        with _CLIENT_LOCK:
            if _HTTP_CLIENT is None:
                _HTTP_CLIENT = httpx.Client(
                    timeout=API_TIMEOUT,
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=20,
                        keepalive_expiry=30.0,
                    ),
                )
    return _HTTP_CLIENT

HTTP_407_RAW = (
    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
    b"Proxy-Authenticate: Basic realm=\"ProxyHub\"\r\n"
    b"Content-Length: 0\r\n"
    b"Connection: close\r\n\r\n"
)


def extract_basic_auth(header_val: Optional[bytes]) -> Tuple[Optional[str], Optional[str]]:
    """Extract (username, password) from Proxy-Authorization: Basic <b64> header."""
    if not header_val:
        return None, None
    try:
        parts = header_val.strip().split(b" ", 1)
        if len(parts) != 2 or parts[0].lower() != b"basic":
            return None, None
        decoded = base64.b64decode(parts[1]).decode("utf-8")
        if ":" in decoded:
            u, p = decoded.split(":", 1)
            return u, p
        return decoded, ""
    except Exception:
        return None, None


def build_407_response_bytes() -> bytes:
    """Raw 407 response bytes sent to client when authentication fails."""
    return HTTP_407_RAW


def create_session_from_api(
    session_url: str,
    api_key: str,
    client_ip: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Optional[Url], Optional[str], Dict[str, Any]]:
    """Call POST /internal/gateway/session to authenticate and get proxy in one round trip.

    Returns (Url, default_target_url, session_meta_dict).
    """
    payload: Dict[str, Any] = {"client_ip": client_ip}
    if username:
        payload["username"] = username
    if password:
        payload["password"] = password

    meta: Dict[str, Any] = {
        "tenant_id": None,
        "credential_id": None,
        "auth_status": "denied",
        "status_code": None,
    }

    try:
        client = get_http_client()
        resp = client.post(
            session_url,
            json=payload,
            headers={"X-Internal-Key": api_key},
            timeout=API_TIMEOUT,
        )
        meta["status_code"] = resp.status_code
    except Exception as e:
        logger.error("Failed to reach backend session API: %s", e)
        return None, None, meta

    if resp.status_code == 401:
        meta["auth_status"] = "denied"
        return None, None, meta

    if resp.status_code != 200:
        logger.warning("Backend session returned %d: %s", resp.status_code, resp.text)
        if resp.status_code == 404:
            meta["auth_status"] = "allowed"
        return None, None, meta

    data = resp.json()
    meta["tenant_id"] = data.get("tenant_id")
    meta["credential_id"] = data.get("credential_id")
    meta["auth_status"] = "allowed"

    proxy_data = data.get("proxy", {})
    auth = ""
    if proxy_data.get("username") and proxy_data.get("password"):
        auth = f"{proxy_data['username']}:{proxy_data['password']}@"
    url_str = f"{proxy_data['scheme']}://{auth}{proxy_data['host']}:{proxy_data['port']}"
    return Url.from_bytes(bytes_(url_str)), data.get("default_target_url"), meta


def send_access_log(payload: Dict[str, Any]) -> None:
    """POST one access-log entry to the backend. Fire-and-forget."""
    try:
        client = get_http_client()
        client.post(
            GATEWAY_LOG_URL,
            json=payload,
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Failed to send access log: %s", e)


class RotateProxyPlugin(TcpUpstreamConnectionHandler, HttpProxyBasePlugin):
    """Authenticates client via session endpoint and proxies through a tenant proxy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._endpoint: Optional[Url] = None
        self._default_target: Optional[str] = None
        self._metadata: List[Any] = [None, None, None, None]
        self._session_meta: Dict[str, Any] = {
            "tenant_id": None,
            "credential_id": None,
            "auth_status": "denied",
        }

    def handle_upstream_data(self, raw: memoryview) -> None:
        self.client.queue(raw)

    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        """Authenticate client and resolve proxy via backend session endpoint."""
        raw_auth = None
        if request.has_header(b"proxy-authorization"):
            raw_auth = request.header(b"proxy-authorization")
        username, password = extract_basic_auth(raw_auth)

        client_ip = "127.0.0.1"
        if hasattr(self.client, "addr") and self.client.addr:
            client_ip = str(self.client.addr[0])

        self._endpoint, self._default_target, self._session_meta = create_session_from_api(
            GATEWAY_SESSION_URL, INTERNAL_API_KEY, client_ip, username, password
        )

        if self._session_meta.get("auth_status") == "denied":
            self.client.queue(memoryview(build_407_response_bytes()))
            self._fire_denied_log(request, client_ip)
            raise HttpProtocolException("Proxy authentication required")

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

    def _fire_denied_log(self, request: HttpParser, client_ip: str) -> None:
        """Send access log entry for rejected authentication attempt."""
        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        method = None if not request.method else request.method.decode()

        _LOG_EXECUTOR.submit(
            send_access_log,
            {
                "tenant_id": None,
                "auth_credential_id": None,
                "auth_status": "denied",
                "client_ip": client_ip,
                "method": method,
                "host": host,
                "path": path,
                "proxy_host": None,
                "proxy_port": None,
                "response_bytes": len(HTTP_407_RAW),
            },
        )

    def handle_client_request(self, request: HttpParser) -> Optional[HttpParser]:
        """Forward request to upstream proxy, stripping client auth and adding upstream auth."""
        if not self.upstream:
            return request

        # Strip client's Proxy-Authorization so upstream proxy doesn't see client creds
        if request.has_header(b"proxy-authorization"):
            request.del_header(b"proxy-authorization")

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

        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        method = None if not request.method else request.method.decode()
        self._metadata = [host, port, path, method]

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
        assert self.upstream
        self.upstream.queue(raw)
        return raw

    def handle_upstream_chunk(self, chunk: memoryview) -> Optional[memoryview]:
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
        _LOG_EXECUTOR.submit(
            send_access_log,
            {
                "tenant_id": self._session_meta.get("tenant_id"),
                "auth_credential_id": self._session_meta.get("credential_id"),
                "auth_status": self._session_meta.get("auth_status", "allowed"),
                "client_ip": context.get("client_ip"),
                "method": self._metadata[3],
                "host": self._metadata[0],
                "path": self._metadata[2],
                "proxy_host": addr,
                "proxy_port": port,
                "response_bytes": self.total_size,
            },
        )
        return None
