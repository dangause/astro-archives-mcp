"""Integration test for vo_sia_fetch through an in-memory FastMCP client.

The backend is mocked (no real HTTP). The test exercises the end-to-end
envelope shape including the resource_uri round-trip via the FastMCP
Resource layer.
"""

import base64

import pytest
from fastmcp import Client

from astro_archives_mcp.tools import sia as sia_tools


class _FakeFetcher:
    def fetch(self, access_url):
        return b"\x00\x01\x02fake-fits-content", "image/fits"


@pytest.mark.asyncio
async def test_vo_sia_fetch_then_resource_read(mcp_server, monkeypatch):
    """End-to-end through in-memory MCP client: call the tool, get a
    resource_uri, read the resource, verify the bytes round-trip."""
    monkeypatch.setattr(sia_tools, "_get_sia", lambda: _FakeFetcher())

    async with Client(mcp_server) as client:
        # 1. Call the tool
        result = await client.call_tool(
            "vo_sia_fetch",
            {
                "access_url": "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/data/pub/x.fits",
            },
        )
        payload = result.structured_content
        assert payload["mime_type"] == "image/fits"
        assert payload["bytes_fetched"] == 20
        uri = payload["resource_uri"]
        assert uri.startswith("resource://results/")

        # 2. Read the resource — bytes round-trip via the FastMCP Resource layer
        contents = await client.read_resource(uri)
        assert len(contents) == 1
        # Per Slice 3 finding: BlobResourceContents.blob is base64-encoded str
        blob = getattr(contents[0], "blob", None) or getattr(contents[0], "text", None)
        if isinstance(blob, str):
            blob = base64.b64decode(blob)
        assert blob == b"\x00\x01\x02fake-fits-content"
