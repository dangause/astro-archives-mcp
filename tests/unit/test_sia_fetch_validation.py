"""Unit tests for vo_sia_fetch's validation logic (SSRF defense)."""

from astro_archives_mcp.errors import ArchiveError
from astro_archives_mcp.tools import sia as sia_tools


class _FakeSiaFetch:
    """Returns a hardcoded (bytes, content_type) tuple, or raises if set."""

    def __init__(self, payload=None, mime="image/fits", exc=None):
        self._payload = payload or b""
        self._mime = mime
        self._exc = exc

    def fetch(self, access_url):
        if self._exc:
            raise self._exc
        return self._payload, self._mime


def test_unknown_host_rejected_as_validation_error(monkeypatch):
    monkeypatch.setattr(sia_tools, "_get_sia", lambda: _FakeSiaFetch())
    out = sia_tools.vo_sia_fetch(access_url="http://internal.example.org/x.fits")
    assert out["error_class"] == "validation_error"
    msg = (out.get("message") or "").lower()
    assert "allow-list" in msg or "known" in msg


def test_malformed_url_rejected_as_validation_error(monkeypatch):
    monkeypatch.setattr(sia_tools, "_get_sia", lambda: _FakeSiaFetch())
    out = sia_tools.vo_sia_fetch(access_url="not-a-url")
    assert out["error_class"] == "validation_error"


def test_known_host_passes_validation_and_returns_envelope(monkeypatch):
    monkeypatch.setattr(
        sia_tools,
        "_get_sia",
        lambda: _FakeSiaFetch(payload=b"\x00\x01\x02fake-fits", mime="image/fits"),
    )
    out = sia_tools.vo_sia_fetch(
        access_url="https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/data/pub/x.fits"
    )
    assert "error_class" not in out
    assert out["resource_uri"].startswith("resource://results/")
    assert out["resource_uri"].endswith(".fits")
    assert out["mime_type"] == "image/fits"
    assert out["source_url"].endswith("/x.fits")
    assert out["bytes_fetched"] == 12
    assert out["archive"] == "cadc"


def test_archive_error_propagates_as_archive_error_class(monkeypatch):
    monkeypatch.setattr(
        sia_tools,
        "_get_sia",
        lambda: _FakeSiaFetch(exc=ArchiveError(message="upstream down")),
    )
    out = sia_tools.vo_sia_fetch(
        access_url="https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/data/pub/x.fits"
    )
    assert out["error_class"] == "archive_error"
