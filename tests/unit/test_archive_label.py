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


def test_unknown_url_derives_label_from_hostname_and_caches():
    url = "https://made-up-archive.example.org/tap"
    assert archive_label(url) == "example"
    # Result memoized under the full URL key.
    assert _CACHE[url] == "example"


def test_hostname_label_strips_subdomains():
    assert archive_label("https://mast.stsci.edu/tap") == "stsci"


def test_hostname_label_handles_multipart_public_suffix():
    # Ordinary 2-label suffix (.de) -> registrable label 'aip'
    assert archive_label("https://tap.gavo.aip.de/tap") == "aip"
    # 'ac.jp' is a multi-label suffix -> registrable label 'nao'
    assert archive_label("https://foo.nao.ac.jp/tap") == "nao"


def test_malformed_or_hostless_url_falls_back_to_other():
    assert archive_label("not-a-url") == "other"


def test_static_hits_skip_hostname_derivation_and_cache():
    url = "https://datalab.noirlab.edu/tap"
    assert archive_label(url) == "datalab"
    # Static map short-circuits before the cache write.
    assert url not in _CACHE


def test_archive_label_never_touches_the_network(monkeypatch):
    """Regression: archive_label must not import or call RegistryClient.
    The cosmetic label is derived offline; a RegTAP scan here was the
    latency footgun this change removed."""
    import astro_archives_mcp.backends.registry as registry_module

    def _boom(*_a, **_k):
        raise AssertionError("archive_label hit the registry/network")

    monkeypatch.setattr(registry_module, "RegistryClient", _boom)
    assert archive_label("https://some-unregistered.example.net/tap") == "example"


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
