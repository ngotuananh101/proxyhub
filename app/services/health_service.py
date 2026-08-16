import time
from dataclasses import dataclass

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


async def check_proxy(proxy: Proxy, url: str, timeout: float) -> CheckResult:
    """GET `url` through the proxy. HTTP response -> alive; error/timeout -> dead."""
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(proxy=build_proxy_url(proxy), timeout=timeout) as client:
            await client.get(url)
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(alive=True, latency_ms=round(latency_ms, 2))
    except Exception:
        return CheckResult(alive=False, latency_ms=None)
