"""Lifecycle tests for vo_tap_status / vo_tap_results / vo_tap_abort
through an in-memory FastMCP client. Backend is faked — no real HTTP."""
from datetime import UTC, datetime

import pytest
from fastmcp import Client

from astro_archives_mcp import _archive_label, job_store
from astro_archives_mcp.tools import tap as tap_tools


class _FakeAsyncJob:
    """Minimal AsyncTAPJob stand-in for test purposes."""

    def __init__(self, phase="EXECUTING", started_at=None, ended_at=None,
                 error_summary=None, table=None):
        self.phase = phase
        self.starttime = started_at
        self.endtime = ended_at
        self._error_summary = error_summary
        self._table = table
        self.deleted = False

    @property
    def error_summary(self):
        return self._error_summary

    def fetch_result(self):
        class _Result:
            def __init__(self, table):
                self._table = table
            def to_table(self):
                return self._table
        return _Result(self._table)

    def delete(self):
        self.deleted = True


class _FakeTapClient:
    """Holds a single fake job; load_job returns it regardless of URL."""

    def __init__(self, job=None):
        self.job = job or _FakeAsyncJob()
        self.submitted = []

    def submit_async(self, *, endpoint, adql, maxrec):
        self.submitted.append((endpoint, adql, maxrec))
        return f"{endpoint}/async/fake-id"

    def load_job(self, job_url):
        return self.job

    def abort_job(self, job_url):
        self.job.delete()

    def query(self, *, endpoint, adql, maxrec):
        raise NotImplementedError("not used in lifecycle tests")


@pytest.fixture(autouse=True)
def _clear_jobs():
    with job_store._LOCK:
        job_store._STORE.clear()
    yield
    with job_store._LOCK:
        job_store._STORE.clear()


@pytest.fixture(autouse=True)
def _offline_archive_label(monkeypatch):
    """Keep tests hermetic: unknown endpoints never call the RegTAP registry.

    archive_label() falls through to pyvo.registry.search for endpoints
    that aren't in the static substring map. We patch that fallback to
    None so tests using example/synthetic endpoints don't hit the
    network (which would be silent in --record-mode=none and brittle
    in CI). Also wipes the in-memory cache so tests are order-
    independent.
    """
    _archive_label._CACHE.clear()
    monkeypatch.setattr(
        _archive_label, "_registry_find_label", lambda _endpoint: None,
    )


@pytest.fixture
def fake_tap(monkeypatch):
    client = _FakeTapClient()
    monkeypatch.setattr(tap_tools, "_get_tap", lambda: client)
    return client


@pytest.mark.asyncio
async def test_status_returns_phase_and_archive(mcp_server, fake_tap):
    job_id, _ = job_store.put(
        job_url="https://datalab.noirlab.edu/tap/async/abc",
        endpoint="https://datalab.noirlab.edu/tap",
        adql="SELECT 1",
    )
    fake_tap.job = _FakeAsyncJob(
        phase="EXECUTING",
        started_at=datetime(2026, 6, 8, 14, 30, tzinfo=UTC),
    )

    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_tap_status", {"job_id": job_id})
        payload = result.structured_content
        assert payload["job_id"] == job_id
        assert payload["phase"] == "EXECUTING"
        assert payload["archive"] == "datalab"
        assert payload["started_at"] == "2026-06-08T14:30:00+00:00"
        assert payload["ended_at"] is None
        assert payload["error_message"] is None


@pytest.mark.asyncio
async def test_status_unknown_job_id_returns_validation_error(mcp_server, fake_tap):
    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "vo_tap_status", {"job_id": "ffffffffffff"},
        )
        payload = result.structured_content
        assert payload["error_class"] == "validation_error"
        assert payload["retry_strategy"] == "abandon"


@pytest.mark.asyncio
async def test_status_phase_error_surfaces_message(mcp_server, fake_tap):
    job_id, _ = job_store.put(
        job_url="https://example.tap/async/abc",
        endpoint="https://example.tap",
        adql="SELECT bogus",
    )

    class _ErrSummary:
        message = "Syntax error near 'bogus'."

    fake_tap.job = _FakeAsyncJob(phase="ERROR", error_summary=_ErrSummary())

    async with Client(mcp_server) as client:
        result = await client.call_tool("vo_tap_status", {"job_id": job_id})
        payload = result.structured_content
        # status itself never raises on ERROR phase — it reports the phase
        # and the message. results is where ERROR raises.
        assert payload["phase"] == "ERROR"
        assert "Syntax error" in payload["error_message"]
