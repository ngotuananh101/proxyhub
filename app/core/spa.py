"""Serve the compiled React dashboard from the API process.

The combined image (``Dockerfile``, ``allinone`` stage) ships both halves of
ProxyHub and exposes a single port, so the backend answers for the dashboard as
well as for the API. The split compose deployment leaves ``FRONTEND_DIST``
empty and lets Nginx serve the SPA, so none of this runs there.

``StaticFiles`` alone is not enough: React Router owns paths such as ``/logs``
that have no file behind them, and reloading one of those must return
``index.html`` rather than a 404.
"""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

# Paths owned by the API. A miss under one of these has to stay a 404 instead
# of falling through to index.html: a client that mistypes an endpoint would
# otherwise get a 200 with an HTML body and fail while parsing JSON.
_RESERVED_PREFIXES = frozenset({"api", "internal", "ws", "docs", "openapi.json", "healthz"})


class SPAStaticFiles(StaticFiles):
    """Static files from the bundle, falling back to index.html for app routes."""

    def __init__(self, directory: str) -> None:
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_client_route(scope):
                raise
            # `html=True` already knows how to read index.html, including its
            # content type and validators.
            return await super().get_response("index.html", scope)


def _is_client_route(scope) -> bool:
    """True when a 404 should become the SPA entry point.

    Only extension-less paths qualify: a request for ``/assets/app-<hash>.js``
    that is no longer in the bundle must stay a 404, or a client holding a
    stale index.html would receive HTML where it expects JavaScript.
    """
    path = scope.get("path", "")
    root = scope.get("root_path", "")
    if root and path.startswith(root):
        path = path[len(root) :]
    path = path.lstrip("/")
    if not path:
        return False
    # Match whole segments: /docs is reserved, /docstore is a client route.
    if path.split("/", 1)[0] in _RESERVED_PREFIXES:
        return False
    return not PurePosixPath(path).suffix
