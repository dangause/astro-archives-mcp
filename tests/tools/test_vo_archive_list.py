"""End-to-end test for vo_archive_list through an in-memory MCP client.

Verifies that the curated KNOWN_ARCHIVES registry — particularly the
usage_notes — surfaces correctly to the LLM via the tool layer.
"""
import pytest
from fastmcp import Client


@pytest.mark.asyncio
async def test_vo_archive_list_returns_curated_set(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_archive_list", {})
        payload = result.structured_content

    assert "archives" in payload
    assert "count" in payload
    assert payload["count"] == len(payload["archives"])
    assert payload["count"] >= 8  # we have 8 well-known archives today

    # First entry should be DataLab (the canonical-example archive),
    # second should be NRAO (primary collaborator, prioritized).
    assert payload["archives"][0]["short_name"] == "datalab"
    assert payload["archives"][1]["short_name"] == "nrao"


@pytest.mark.asyncio
async def test_vo_archive_list_nrao_entry_carries_async_usage_note(mcp_server):
    """The most operationally important note: NRAO needs mode='async'
    for data queries. If this regresses, the LLM falls back to the
    trial-and-error loop we built this tool to avoid."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_archive_list", {})
        payload = result.structured_content

    nrao = next(a for a in payload["archives"] if a["short_name"] == "nrao")
    notes_joined = " ".join(nrao["usage_notes"]).lower()

    # Three load-bearing facts must reach the LLM:
    assert "async" in notes_joined, "NRAO note about mode='async' missing"
    assert "tap_schema.obscore" in notes_joined, "NRAO non-standard obscore location missing"
    assert "3c218" in notes_joined or "radio designation" in notes_joined, (
        "NRAO target-aliasing note missing — LLM will fail on 'Hydra-A' lookups"
    )


@pytest.mark.asyncio
async def test_vo_archive_list_serializes_tuple_fields_as_lists(mcp_server):
    """Tuples in the dataclass must come out as JSON-friendly lists."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_archive_list", {})
        payload = result.structured_content

    for entry in payload["archives"]:
        assert isinstance(entry["host_substrings"], list)
        assert isinstance(entry["notable_tables"], list)
        assert isinstance(entry["usage_notes"], list)


@pytest.mark.asyncio
async def test_vo_archive_list_includes_capabilities_for_each_archive(mcp_server):
    """Every entry should at minimum identify itself by short_name +
    display_name and expose the protocol URL fields (even when None)."""
    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_archive_list", {})
        payload = result.structured_content

    required_keys = {
        "short_name", "display_name", "host_substrings",
        "tap_url", "sia_url", "scs_url",
        "waveband", "description", "notable_tables", "usage_notes",
    }
    for entry in payload["archives"]:
        assert required_keys.issubset(entry.keys()), (
            f"archive {entry.get('short_name')} missing keys: "
            f"{required_keys - entry.keys()}"
        )
