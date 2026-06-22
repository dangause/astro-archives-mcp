from unittest.mock import patch

import pytest

from astro_archives_mcp import _archive_label
from astro_archives_mcp._archive_label import _CACHE, archive_label


@pytest.fixture(autouse=True)
def clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


def test_static_fastpath_hit_datalab():
    assert archive_label("https://datalab.noirlab.edu/tap") == "datalab"


def test_static_fastpath_hit_alma():
    assert archive_label("https://almascience.nrao.edu/tap") == "alma"


def test_unknown_url_falls_back_to_registry_then_caches():
    fake_url = "https://made-up-archive.example.org/tap"
    with patch.object(_archive_label, "_registry_find_label", return_value="madeup") as mock_find:
        first = archive_label(fake_url)
        second = archive_label(fake_url)
    assert first == "madeup"
    assert second == "madeup"
    # Registry was hit exactly once — cache held the result
    assert mock_find.call_count == 1


def test_registry_not_found_caches_other_no_retry():
    fake_url = "https://truly-unknown.example.org/tap"
    with patch.object(_archive_label, "_registry_find_label", return_value=None) as mock_find:
        first = archive_label(fake_url)
        second = archive_label(fake_url)
    assert first == "other"
    assert second == "other"
    assert mock_find.call_count == 1


def test_static_hits_skip_registry_entirely():
    with patch.object(
        _archive_label, "_registry_find_label", return_value="should-not-fire"
    ) as mock_find:
        assert archive_label("https://datalab.noirlab.edu/tap") == "datalab"
    assert mock_find.call_count == 0


def test_is_known_archive_url_known_host():
    assert _archive_label.is_known_archive_url("https://datalab.noirlab.edu/sia/x") is True
    assert _archive_label.is_known_archive_url("https://archive.eso.org/sia/y") is True
    assert (
        _archive_label.is_known_archive_url(
            "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/data/pub/z"
        )
        is True
    )


def test_is_known_archive_url_unknown_host():
    assert _archive_label.is_known_archive_url("http://internal.example.org/x") is False
    assert _archive_label.is_known_archive_url("https://random-host.com/y") is False


def test_is_known_archive_url_does_not_consult_registry_cache():
    """Cache-warming defense: even if a URL is cached in _CACHE from
    a previous registry lookup, is_known_archive_url returns False
    unless it's in the static map."""
    fake_url = "https://truly-unknown.example.org/tap"
    _archive_label._CACHE[fake_url] = "fake_label"
    try:
        assert _archive_label.is_known_archive_url(fake_url) is False
    finally:
        _archive_label._CACHE.pop(fake_url, None)


def test_is_known_archive_url_malformed_url():
    assert _archive_label.is_known_archive_url("not-a-url") is False
    assert _archive_label.is_known_archive_url("") is False


def test_is_known_archive_url_heidelberg_gaia_is_allowed():
    """Slice 2 cassettes use this host; Slice 4 must allow it for fetch too."""
    assert _archive_label.is_known_archive_url("https://gaia.ari.uni-heidelberg.de/cone/x") is True
