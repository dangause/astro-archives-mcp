import pytest

from astro_archives_mcp.backends.registry import RegistryClient
from astro_archives_mcp.errors import ValidationError

# Choose a known-stable IVOID for cassette recording.
# Pre-flight against pyvo 1.8 RegTAP showed the plan's ``ivo://datalab/smash_dr2``
# does not resolve; the real DataLab TAP service is registered as below.
DATALAB_TAP_IVOID = "ivo://noirlab.edu/datalab/tap"
DATALAB_TAP_URL = "https://datalab.noirlab.edu/tap"

# Use ESO TAP_obs for describe-by-IVOID and describe-by-URL: ~58 tables,
# cassette stays small. The DataLab TAP has 4027 tables and produced
# 22 MB cassettes, so we switched the describe tests to ESO.
ESO_TAP_OBS_URL = "https://archive.eso.org/tap_obs"
ESO_TAP_OBS_IVOID = "ivo://eso.org/tap_obs"


@pytest.mark.vcr
def test_search_by_keyword_returns_services():
    client = RegistryClient()
    out = client.search(keywords=["smash"], servicetype=None, waveband=None, maxrec=5)
    assert isinstance(out, list)
    assert len(out) >= 1
    assert any("smash" in (s.get("title") or "").lower() for s in out)
    first = out[0]
    for key in ("ivoid", "title", "description", "publisher",
                "tap_url", "sia_url", "scs_url", "ssa_url", "waveband"):
        assert key in first


@pytest.mark.vcr
def test_describe_by_ivoid_returns_tap_schema():
    client = RegistryClient()
    out = client.describe(ivoid_or_url=ESO_TAP_OBS_IVOID)
    assert out["ivoid"] == ESO_TAP_OBS_IVOID
    assert "tap" in out["capabilities"]
    assert len(out["tables"]) >= 1
    cols = out["tables"][0]["columns"]
    assert len(cols) >= 1
    assert {"name", "type"}.issubset(cols[0].keys())


@pytest.mark.vcr
def test_describe_by_tap_url_returns_tap_schema():
    client = RegistryClient()
    out = client.describe(ivoid_or_url=ESO_TAP_OBS_URL)
    assert "tap" in out["capabilities"]
    assert len(out["tables"]) >= 1


def test_describe_rejects_garbage_input():
    client = RegistryClient()
    with pytest.raises(ValidationError) as exc:
        client.describe(ivoid_or_url="not-an-ivoid-or-url")
    assert "ivo://" in exc.value.message or "URL" in exc.value.message


@pytest.mark.vcr
def test_find_label_for_datalab_tap_returns_short_name():
    client = RegistryClient()
    label = client.find_label(DATALAB_TAP_URL)
    assert label is not None
    assert isinstance(label, str)
    assert len(label) > 0


def test_find_label_swallows_registry_errors_and_returns_none(monkeypatch):
    from pyvo.dal.exceptions import DALServiceError

    from astro_archives_mcp.backends import registry as registry_module

    def fake_search(**_kw):
        raise DALServiceError("registry down")

    monkeypatch.setattr(registry_module.pyvo.registry, "search", fake_search)
    client = RegistryClient()
    label = client.find_label("https://anything.example.org/tap")
    assert label is None
