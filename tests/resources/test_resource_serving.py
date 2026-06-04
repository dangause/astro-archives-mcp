import base64
import time

import pytest
from fastmcp import Client
from mcp.shared.exceptions import McpError

from astro_archives_mcp import result_store


@pytest.fixture(autouse=True)
def clear_store():
    result_store._STORE.clear()
    yield
    result_store._STORE.clear()


@pytest.mark.asyncio
async def test_resource_serves_stored_bytes(mcp_server):
    # Pre-load the store
    uuid, _ = result_store.put(b"parquet-bytes-payload")
    uri = f"resource://results/{uuid}.parquet"

    async with Client(mcp_server) as client:
        contents = await client.read_resource(uri)
        # FastMCP 3.3.1 returns a list of BlobResourceContents; binary bodies
        # are transported per the MCP spec as base64-encoded strings on the
        # `blob` attribute. Text-only resources would use `text` instead.
        assert len(contents) == 1
        blob = getattr(contents[0], "blob", None)
        if blob is not None:
            # base64-encoded string per MCP spec
            assert isinstance(blob, str)
            payload = base64.b64decode(blob)
        else:
            text = getattr(contents[0], "text", None)
            payload = text.encode("utf-8") if isinstance(text, str) else text
        assert payload == b"parquet-bytes-payload"


@pytest.mark.asyncio
async def test_resource_missing_uuid_raises(mcp_server):
    uri = "resource://results/000000000000.parquet"
    async with Client(mcp_server) as client:
        # FastMCP 3.3.1 surfaces unknown / failed reads as mcp.McpError.
        with pytest.raises(McpError):
            await client.read_resource(uri)


@pytest.mark.asyncio
async def test_resource_expired_uuid_raises(mcp_server):
    # Store with a very short TTL, sleep past it, then read
    uuid, _ = result_store.put(b"x", ttl_seconds=0.01)
    time.sleep(0.05)
    uri = f"resource://results/{uuid}.parquet"
    async with Client(mcp_server) as client:
        with pytest.raises(McpError):
            await client.read_resource(uri)


@pytest.mark.asyncio
async def test_resource_mime_type_is_parquet(mcp_server):
    uuid, _ = result_store.put(b"x")
    uri = f"resource://results/{uuid}.parquet"
    async with Client(mcp_server) as client:
        contents = await client.read_resource(uri)
        mime = getattr(contents[0], "mimeType", None) or getattr(contents[0], "mime_type", None)
        assert mime == "application/vnd.apache.parquet"
