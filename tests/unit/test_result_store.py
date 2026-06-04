import time
from datetime import UTC, datetime, timedelta

import pytest

from astro_archives_mcp import result_store


@pytest.fixture(autouse=True)
def clear_store():
    """Hermetic tests: clear the module-level dict between runs."""
    result_store._STORE.clear()
    yield
    result_store._STORE.clear()


def test_put_and_get_roundtrip():
    uuid, expires_at = result_store.put(b"hello world", "text/plain")
    assert isinstance(uuid, str)
    assert len(uuid) > 0
    assert isinstance(expires_at, datetime)
    assert expires_at.tzinfo is not None  # MUST be timezone-aware
    result = result_store.get(uuid)
    assert result is not None
    payload, mime = result
    assert payload == b"hello world"
    assert mime == "text/plain"


def test_get_unknown_returns_none():
    assert result_store.get("nonexistent-uuid") is None


def test_get_expired_returns_none_and_evicts():
    uuid, _ = result_store.put(b"payload", "application/octet-stream", ttl_seconds=0.05)
    time.sleep(0.1)
    assert result_store.get(uuid) is None
    # Entry was evicted by the check-on-read
    assert uuid not in result_store._STORE


def test_put_returns_unique_uuids():
    uuid_a, _ = result_store.put(b"a", "application/octet-stream")
    uuid_b, _ = result_store.put(b"b", "application/octet-stream")
    assert uuid_a != uuid_b


def test_size_estimate_sums_bytes_and_counts_entries():
    result_store.put(b"x" * 100, "application/octet-stream")
    result_store.put(b"y" * 200, "application/octet-stream")
    summary = result_store.size_estimate()
    assert summary["entries"] == 2
    assert summary["bytes"] == 300


def test_expires_at_reflects_ttl():
    before = datetime.now(UTC)
    _, expires_at = result_store.put(b"x", "application/octet-stream", ttl_seconds=600)
    after = datetime.now(UTC)
    expected_min = before + timedelta(seconds=599)
    expected_max = after + timedelta(seconds=601)
    assert expected_min <= expires_at <= expected_max


def test_put_with_fits_mime_returns_fits_on_get():
    uuid, _ = result_store.put(b"fake fits bytes", "image/fits")
    result = result_store.get(uuid)
    assert result is not None
    payload, mime = result
    assert payload == b"fake fits bytes"
    assert mime == "image/fits"
