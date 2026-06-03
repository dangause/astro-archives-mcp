"""Compose the FastMCP server and mount it under Starlette with health probes."""
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from astro_archives_mcp import __version__
from astro_archives_mcp.observability import (
    configure_logging,
    current_request_id,
    new_request_id,
)
from astro_archives_mcp.tools.ivoa import vo_tap_query


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Set ``current_request_id`` for the duration of each inbound HTTP request.

    The in-memory MCP client bypasses Starlette, so tool code reading the
    ContextVar in those tests sees ``None``. That is fine — tools tolerate the
    missing ID and the integration test does not assert on it.
    """

    async def dispatch(self, request, call_next):
        token = current_request_id.set(new_request_id())
        try:
            return await call_next(request)
        finally:
            current_request_id.reset(token)


def build_mcp() -> FastMCP:
    """Construct the FastMCP server with all Slice-A tools registered."""
    mcp = FastMCP(name="astro-archives-mcp")
    mcp.tool(vo_tap_query)
    return mcp


def build_app() -> Starlette:
    configure_logging()
    mcp = build_mcp()

    async def health(_request):
        return JSONResponse({"status": "ok", "version": __version__})

    async def ready(_request):
        # Slice A: no backend pre-warm. Later slices ping a known TAP endpoint.
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/ready", ready),
            Mount("/mcp", app=mcp.http_app()),
        ],
        middleware=[Middleware(RequestIdMiddleware)],
    )
