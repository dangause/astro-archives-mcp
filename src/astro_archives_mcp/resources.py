"""FastMCP Resource registration for result_store-backed Parquet payloads.

A single Resource URI template `resource://results/{uuid}.parquet` is
registered. The handler looks up bytes in `result_store` and returns
them with the Parquet MIME type.

If the UUID is unknown or expired, FastMCP surfaces an MCP-protocol-level
error to the client (the URI cannot be read). This is NOT a tool
execution error — Resource serving is a different MCP primitive.

Note on MIME type: FastMCP 3.3.1 honors the `mime_type` kwarg on the
resource template (visible to `resources/listResourceTemplates`), but
when a handler returns raw `bytes` the per-read MIME type is forced to
`application/octet-stream`. To make the per-blob `mimeType` reflect
Parquet, the handler returns a `ResourceResult` containing a
`ResourceContent` with an explicit `mime_type`.
"""

import logging

from fastmcp import FastMCP
from fastmcp.resources import ResourceContent, ResourceResult

from astro_archives_mcp import result_store

log = logging.getLogger(__name__)

PARQUET_MIME = "application/vnd.apache.parquet"


def register_resources(mcp: FastMCP) -> None:
    """Wire result_store reads into MCP Resource serving."""

    @mcp.resource(
        "resource://results/{uuid}.parquet",
        mime_type=PARQUET_MIME,
    )
    def serve_result(uuid: str) -> ResourceResult:
        entry = result_store.get(uuid)
        if entry is None:
            log.warning("result_store: resource miss for %s (expired or never stored)", uuid)
            # FastMCP surfaces a missing-resource error to the client.
            # The exact exception type depends on the version; raising
            # ValueError is acceptable — FastMCP wraps it.
            raise ValueError(f"resource://results/{uuid}.parquet not found")
        payload, _mime = entry
        return ResourceResult(
            contents=[ResourceContent(payload, mime_type=PARQUET_MIME)],
        )
