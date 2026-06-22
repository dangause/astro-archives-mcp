"""vo_tap_query mode parameter + auto-promote behavior."""

import pytest
from astropy.table import Table
from fastmcp import Client

from astro_archives_mcp import _archive_label, job_store
from astro_archives_mcp.errors import ArchiveError
from astro_archives_mcp.tools import tap as tap_tools


class _FakeTapClient:
    def __init__(self):
        self.query_table = Table({"ra": [1.0], "dec": [2.0]})
        self.query_raises = None
        self.submit_returns = "https://datalab.noirlab.edu/tap/async/auto-promoted"
        self.submit_calls = 0

    def query(self, *, endpoint, adql, maxrec):
        if self.query_raises is not None:
            raise self.query_raises
        return self.query_table

    def submit_async(self, *, endpoint, adql, maxrec):
        self.submit_calls += 1
        return self.submit_returns

    def load_job(self, job_url):
        class _J:
            phase = "EXECUTING"
            starttime = None
            endtime = None
            error_summary = None

        return _J()

    def abort_job(self, job_url):
        pass


@pytest.fixture(autouse=True)
def _clear_jobs():
    with job_store._LOCK:
        job_store._STORE.clear()
    yield
    with job_store._LOCK:
        job_store._STORE.clear()


@pytest.fixture(autouse=True)
def _offline_archive_label(monkeypatch):
    """Keep tests hermetic — unknown endpoints don't call RegTAP."""
    _archive_label._CACHE.clear()
    monkeypatch.setattr(
        _archive_label,
        "_registry_find_label",
        lambda _endpoint: None,
    )


@pytest.fixture
def fake_tap(monkeypatch):
    client = _FakeTapClient()
    monkeypatch.setattr(tap_tools, "_get_tap", lambda: client)
    return client


@pytest.mark.asyncio
async def test_mode_sync_returns_inline_envelope(mcp_server, fake_tap):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT 1",
                "mode": "sync",
            },
        )
        payload = result.structured_content
        assert "mode" not in payload  # sync envelope is mode-less
        assert payload["row_count"] == 1
        assert payload["rows"] == [[1.0, 2.0]]

    assert job_store.size_estimate()["entries"] == 0
    assert fake_tap.submit_calls == 0


@pytest.mark.asyncio
async def test_mode_auto_fast_returns_inline_no_promotion(mcp_server, fake_tap):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT 1",
                "mode": "auto",
            },
        )
        payload = result.structured_content
        assert "mode" not in payload
        assert payload["row_count"] == 1

    assert job_store.size_estimate()["entries"] == 0


@pytest.mark.asyncio
async def test_mode_auto_promotes_on_timeout(mcp_server, fake_tap):
    fake_tap.query_raises = ArchiveError(message="TAP sync request timed out: read timeout")

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT slow_join",
                "mode": "auto",
            },
        )
        payload = result.structured_content
        assert payload["mode"] == "async"
        assert payload["archive"] == "datalab"
        assert payload["phase"] == "EXECUTING"
        assert len(payload["job_id"]) == 12

    assert job_store.size_estimate()["entries"] == 1
    assert fake_tap.submit_calls == 1


@pytest.mark.asyncio
async def test_mode_auto_does_not_promote_on_syntax_error(mcp_server, fake_tap):
    from astro_archives_mcp.errors import DalQueryError

    fake_tap.query_raises = DalQueryError(message="Bad ADQL syntax.")

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT BAD",
                "mode": "auto",
            },
        )
        payload = result.structured_content
        # DalQueryError must propagate unchanged in auto mode — promotion
        # only fires for the timeout failure mode.
        assert payload["error_class"] == "tap_query_error"
        assert fake_tap.submit_calls == 0


@pytest.mark.asyncio
async def test_mode_sync_propagates_timeout_as_archive_error(mcp_server, fake_tap):
    fake_tap.query_raises = ArchiveError(message="TAP sync request timed out.")

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://datalab.noirlab.edu/tap",
                "adql": "SELECT 1",
                "mode": "sync",
            },
        )
        payload = result.structured_content
        assert payload["error_class"] == "archive_error"
        assert payload["retry_strategy"] == "wait_and_retry"

    assert job_store.size_estimate()["entries"] == 0
    assert fake_tap.submit_calls == 0


@pytest.mark.asyncio
async def test_mode_async_skips_sync_and_returns_promotion(mcp_server, fake_tap):
    fake_tap.query_raises = RuntimeError("query() must not be called in mode=async")

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_query",
            {
                "endpoint": "https://almascience.nrao.edu/tap",
                "adql": "SELECT TOP 1 * FROM ivoa.obscore",
                "mode": "async",
            },
        )
        payload = result.structured_content
        assert payload["mode"] == "async"
        assert payload["archive"] == "alma"
        assert payload["phase"] == "EXECUTING"

    assert job_store.size_estimate()["entries"] == 1
