"""End-to-end integration test for vo_tap_query through an in-memory MCP client.

The test mounts the real FastMCP server (via the ``mcp_server`` fixture) and
talks to it with ``fastmcp.Client``. Network traffic is recorded with vcrpy.
"""
import pytest
from fastmcp import Client

from astro_archives_mcp.errors import TapQueryError, ValidationError
from astro_archives_mcp.tools import ivoa as ivoa_tools


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
        # structured_content instead, the discriminator is `error_class`.
        if result.is_error:
            content_text = "".join(getattr(c, "text", "") for c in result.content)
            assert "maxrec" in content_text
        else:
            payload = result.structured_content
            assert payload.get("error_class") is not None


class _FakeTap:
    def __init__(self, exc):
        self._exc = exc

    def query(self, **_kw):
        raise self._exc


@pytest.mark.parametrize(
    ("exc", "expected_error_class"),
    [
        (TapQueryError(message="column not found"), "tap_query_error"),
        (ValidationError(message="bad endpoint", hint="see docs"), "validation_error"),
        (RuntimeError("upstream blew up"), "internal_error"),
    ],
)
def test_vo_tap_query_error_path_returns_structured_payload(
    exc, expected_error_class, monkeypatch
):
    """When the backend raises, vo_tap_query returns a structured payload
    keyed on ``error_class`` (NOT ``isError``). The protocol-level
    ``is_error`` flag is FastMCP's separate concern.
    """
    monkeypatch.setattr(ivoa_tools, "_get_tap", lambda: _FakeTap(exc))
    payload = ivoa_tools.vo_tap_query(
        endpoint="https://datalab.noirlab.edu/tap",
        adql="SELECT 1",
        maxrec=10,
    )
    assert "isError" not in payload, "isError key should not be in the payload (see ivoa.py docstring)"
    assert payload["error_class"] == expected_error_class
    assert "retry_strategy" in payload
