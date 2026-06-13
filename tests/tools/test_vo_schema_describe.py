"""End-to-end test for vo_schema_describe through an in-memory MCP client.

Verifies the spec §4.1 envelope shape, including the staleness
mechanism (last_verified / stale / stale_days) and the omit-on-miss
convention.
"""
from datetime import date

import pytest
from fastmcp import Client

from astro_archives_mcp.tools import knowledge as knowledge_tool  # noqa: F401


@pytest.mark.asyncio
async def test_known_entry_returns_envelope_with_curated_fields(mcp_server):
    """The marquee NRAO obscore entry — pins the load-bearing
    structured fields (enums, missing_standard_columns) so a
    regression in the seed data fails this test loudly."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "nrao", "table": "tap_schema.obscore"},
        )
        payload = result.structured_content

    assert payload["known"] is True
    assert payload["archive"] == "nrao"
    assert payload["table"] == "tap_schema.obscore"
    assert "dataproduct_subtype" in payload["missing_standard_columns"]
    assert payload["value_enums"]["instrument_name"] == [
        "EVLA", "VLA", "VLBA", "GBT",
    ]
    assert payload["value_enums"]["facility_name"] == ["NRAO"]


@pytest.mark.asyncio
async def test_known_entry_includes_staleness_fields(mcp_server):
    """last_verified, stale, stale_days are all present and
    well-typed."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "nrao", "table": "tap_schema.obscore"},
        )
        payload = result.structured_content

    # Date is serialized as ISO 8601 string
    assert isinstance(payload["last_verified"], str)
    date.fromisoformat(payload["last_verified"])  # parses cleanly
    assert isinstance(payload["stale"], bool)
    assert isinstance(payload["stale_days"], int)
    assert payload["stale_days"] >= 0


@pytest.mark.asyncio
async def test_known_entry_returns_stale_true_when_threshold_exceeded(
    mcp_server, monkeypatch,
):
    """Tighten the staleness threshold to 0 days so any entry reads
    as stale. Pins the comparison logic."""
    from astro_archives_mcp.tools import knowledge as kt
    monkeypatch.setattr(kt, "_staleness_days_threshold", lambda: 0)

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "nrao", "table": "tap_schema.obscore"},
        )
        payload = result.structured_content

    assert payload["known"] is True
    assert payload["stale"] is True


@pytest.mark.asyncio
async def test_known_entry_returns_stale_false_when_recent(mcp_server):
    """With the default 90-day threshold and a recent seed date, the
    NRAO entry must not read as stale at ship time."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "nrao", "table": "tap_schema.obscore"},
        )
        payload = result.structured_content

    assert payload["stale"] is False


@pytest.mark.asyncio
async def test_unknown_pair_returns_known_false_with_no_other_keys(mcp_server):
    """Spec §4.1 omit-on-miss: when known=false, no other Schema
    fields appear in the envelope."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "bogus", "table": "bogus.bogus"},
        )
        payload = result.structured_content

    assert payload == {
        "known": False,
        "archive": "bogus",
        "table": "bogus.bogus",
    }


@pytest.mark.asyncio
async def test_empty_archive_returns_validation_error(mcp_server):
    """Empty input is a validation error, not a soft-miss."""
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_schema_describe",
            {"archive": "", "table": "tap_schema.obscore"},
        )
        payload = result.structured_content

    assert payload["error_class"] == "validation_error"
    assert payload["retry_strategy"] == "fix_and_retry"
