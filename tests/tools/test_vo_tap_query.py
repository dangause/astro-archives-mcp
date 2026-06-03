"""End-to-end integration test for vo_tap_query through an in-memory MCP client.

The test mounts the real FastMCP server (via the ``mcp_server`` fixture) and
talks to it with ``fastmcp.Client``. Network traffic is recorded with vcrpy.
"""
import pytest
from fastmcp import Client


@pytest.mark.vcr
async def test_vo_tap_query_via_in_memory_client(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": (
                    "SELECT TOP 3 ra, dec FROM smash_dr2.object "
                    "WHERE ra BETWEEN 185 AND 185.01 ORDER BY ra"
                ),
                "maxrec": 10,
            },
        )
        payload = result.structured_content
        assert payload["row_count"] <= 3
        assert payload["truncated"] is False
        assert payload["archive"] == "datalab"
        names = {c["name"] for c in payload["columns"]}
        assert {"ra", "dec"}.issubset(names)


async def test_vo_tap_query_validation_error_surface(mcp_server):
    async with Client(mcp_server) as client:
        # raise_on_error=False so we can inspect the surfaced error shape
        # rather than catching the framework-level ToolError exception.
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT TOP 3 ra FROM x",
                "maxrec": -1,  # violates Field(ge=1)
            },
            raise_on_error=False,
        )
        # FastMCP 3.3.1 surfaces Pydantic validation as a framework-level tool
        # error: is_error=True with the message in result.content (TextContent).
        # If a future version starts shipping our error payload through
        # structured_content instead, accept that shape too.
        if result.is_error:
            content_text = "".join(getattr(c, "text", "") for c in result.content)
            assert "maxrec" in content_text
        else:
            payload = result.structured_content
            assert payload.get("isError") is True
