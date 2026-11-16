import time
from dataclasses import dataclass
from functools import lru_cache
from ssl import SSLContext

import httpx

from app.models.proxy import Proxy


@dataclass
class CheckResult:
    alive: bool
    latency_ms: float | None


def build_proxy_url(proxy: Proxy) -> str:
    if proxy.username and proxy.password:
        return f"{proxy.scheme}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
    return f"{proxy.scheme}://{proxy.host}:{proxy.port}"


@lru_cache(maxsize=1)
def get_ssl_context() -> SSLContext:
    """Return the process-wide TLS context used for health checks.

    httpx builds a fresh context per client when `verify=True`, which parses the
    whole CA bundle — ~7 ms of blocking work on the event loop. Each check needs
    its own client (every proxy has a different upstream), so the context is the
    part that can be shared. With one context, building a client costs ~0.15 ms.
    """
    return httpx.create_ssl_context()


async def check_proxy(proxy: Proxy, url: str, timeout: float) -> CheckResult:
    """GET `url` through the proxy. HTTP response -> alive; error/timeout -> dead."""
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            proxy=build_proxy_url(proxy),
            timeout=timeout,
            verify=get_ssl_context(),
        ) as client:
            await client.get(url)
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(alive=True, latency_ms=round(latency_ms, 2))
    except Exception:
        return CheckResult(alive=False, latency_ms=None)
