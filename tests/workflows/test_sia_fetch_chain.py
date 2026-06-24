"""End-to-end workflow: SIA search → pick access_url → fetch → read Resource.

What the LLM does when asked "download an image of source X from CADC":

    1. vo_sia_search(endpoint, ra, dec, size_deg) → table rows
    2. Pick an access_url from the rows (or follow CADC's datalink — that's
       another chain; tested separately).
    3. vo_sia_fetch(access_url)  → resource_uri envelope
    4. read_resource(resource_uri) → bytes round-trip

The backend is faked. The interesting things to pin:

- The access_url the LLM gets from search is a valid input for fetch.
- The SSRF allow-list gate fires correctly.
- The Resource layer round-trips the bytes (base64 vs raw vs text).
- MIME type is preserved end-to-end.
"""

import base64

import pytest
from astropy.table import Table
from fastmcp import Client

from astro_archives_mcp.tools import sia as sia_tools

CADC_SIA = "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/sia"


class _FakeSiaClient:
    """Stand-in for SiaClient that returns deterministic search results +
    bytes for fetch."""

    def __init__(self):
        # A minimal SIA2 result with the columns the LLM would actually use.
        self._search_table = Table(
            {
                "obs_id": ["test-1", "test-2"],
                "target_name": ["NGC 4258", "NGC 4258"],
                "instrument_name": ["TESS-cam", "TESS-cam"],
                "access_url": [
                    f"{CADC_SIA}/file/test-1.fits",
                    f"{CADC_SIA}/file/test-2.fits",
                ],
                "access_format": ["image/fits", "image/fits"],
            }
        )
        # Map of access_url → (bytes, mime_type).
        self._files = {
            f"{CADC_SIA}/file/test-1.fits": (
                b"SIMPLE  =                    T / minimal fake FITS",
                "image/fits",
            ),
            f"{CADC_SIA}/file/test-2.fits": (
                b"different bytes for test-2",
                "image/fits",
            ),
        }

    def search(self, **_kwargs):
        return self._search_table

    def fetch(self, access_url: str):
        if access_url not in self._files:
            raise RuntimeError(f"Fake SIA client does not know URL: {access_url}")
        return self._files[access_url]


@pytest.fixture
def fake_sia(monkeypatch):
    client = _FakeSiaClient()
    monkeypatch.setattr(sia_tools, "_get_sia", lambda: client)
    return client


@pytest.mark.asyncio
async def test_search_then_fetch_then_read_resource(mcp_server, fake_sia):
    """The headline chain end-to-end. The bytes the LLM eventually
    reads via the Resource must match what `fake_sia.fetch` returned."""
    async with Client(mcp_server) as client:
        # Step 1: search
        search = await client.call_tool(
            "vo_sia_search",
            {
                "endpoint": CADC_SIA,
                "ra": 184.74,
                "dec": 47.30,
                "size_deg": 0.05,
            },
        )
        sp = search.structured_content
        assert sp["row_count"] == 2
        col_names = [c["name"] for c in sp["columns"]]
        assert "access_url" in col_names

        # Step 2: pick the first access_url (the LLM's natural move)
        access_url_idx = col_names.index("access_url")
        first_access_url = sp["rows"][0][access_url_idx]
        assert first_access_url == f"{CADC_SIA}/file/test-1.fits"

        # Step 3: fetch
        fetch = await client.call_tool(
            "vo_sia_fetch",
            {"access_url": first_access_url},
        )
        fp = fetch.structured_content
        assert fp["mime_type"] == "image/fits"
        assert fp["bytes_fetched"] == len(b"SIMPLE  =                    T / minimal fake FITS")
        assert fp["source_url"] == first_access_url
        resource_uri = fp["resource_uri"]
        assert resource_uri.startswith("resource://results/")

        # Step 4: read the Resource → bytes round-trip
        contents = await client.read_resource(resource_uri)
        assert len(contents) == 1
        blob = getattr(contents[0], "blob", None) or getattr(contents[0], "text", None)
        if isinstance(blob, str):
            blob = base64.b64decode(blob)
        assert blob == b"SIMPLE  =                    T / minimal fake FITS"


@pytest.mark.asyncio
async def test_chain_blocks_ssrf_when_url_not_in_allow_list(mcp_server, fake_sia):
    """Pick a URL from a search BUT then try to fetch one from outside
    the known-archive allow-list. The SSRF defense must fire."""
    async with Client(mcp_server) as client:
        await client.call_tool(
            "vo_sia_search",
            {"endpoint": CADC_SIA, "ra": 184.74, "dec": 47.30, "size_deg": 0.05},
        )
        # Try to fetch from a host not in known_archives
        result = await client.call_tool(
            "vo_sia_fetch",
            {"access_url": "https://evil.example.com/fake.fits"},
        )
        rp = result.structured_content
        assert rp["error_class"] == "validation_error"
        assert rp["retry_strategy"] == "abandon"
        assert "allow-list" in rp["message"].lower()


@pytest.mark.asyncio
async def test_chain_preserves_mime_type_through_resource_layer(mcp_server, fake_sia):
    """If we extend `fake_sia.fetch` to return a different MIME, the
    Resource read must echo it back. This pins the round-trip for the
    CADC datalink case where bytes are VOTable not FITS."""
    # Replace one file with a VOTable-flavored response
    votable_bytes = b'<?xml version="1.0"?><VOTABLE><RESOURCE/></VOTABLE>'
    fake_sia._files[f"{CADC_SIA}/file/test-1.fits"] = (
        votable_bytes,
        "application/x-votable+xml",
    )

    async with Client(mcp_server) as client:
        fetch = await client.call_tool(
            "vo_sia_fetch",
            {"access_url": f"{CADC_SIA}/file/test-1.fits"},
        )
        fp = fetch.structured_content
        assert fp["mime_type"] == "application/x-votable+xml"

        contents = await client.read_resource(fp["resource_uri"])
        # MCP envelope should also reflect the right MIME on read.
        assert getattr(contents[0], "mimeType", None) == "application/x-votable+xml"
